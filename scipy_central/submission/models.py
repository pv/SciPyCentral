from django.db import models
from django.db.models import signals
from django.core.urlresolvers import reverse
from django.template.defaultfilters import slugify

from scipy_central.person.models import User
from scipy_central.pagehit.models import PageHit

class License(models.Model):
    """
    License for the submission
    """
    name = models.CharField(max_length=255,
                            help_text="License used for code submissions.")
    slug = models.SlugField(max_length=255, editable=False)

    description = models.TextField(help_text="Short description of license")
    text_template = models.TextField(help_text=('Full license text with ',
                                                'template fields'))

    def __unicode__(self):
        return self.name

    class Meta:
        permissions = (("can_edit", "Can edit this license"),)


class SubmissionManager(models.Manager):
    def create_without_commit(self, **kwargs):
        """
        Uses code from django.db.models.create(...) to create a new instance
        without writing to the database.

        To save the object to the database (presumably after validating it, or
        doing some other checks), you can call the ``obj.save()`` method. E.g.:

            obj = models.Submission.objects.create_without_commit(....)
            ...
            ...
            obj.save(force_insert=True, using=models.Submission.objects.db)
            # or
            obj.save(force_insert=True)
        """
        qs = self.get_query_set()
        obj = qs.model(**kwargs)
        self._for_write = True
        #obj.save(force_insert=True, using=self.db)
        return obj


class Submission(models.Model):
    """
    A single model for all submission types. Most of the information is stored
    in the ``Revision`` for the submission, allowing us to store a history of
    the submission in consecutive revisions.
    """
    objects = SubmissionManager()
    # Submission type
    SUBMISSION_TYPE = (
        ('snippet', 'Code snippet'),
        ('package', 'Code library/package'),
        ('link',    'Remote link'),
    )
    sub_type = models.CharField(max_length=10, choices=SUBMISSION_TYPE,
                help_text = 'Your submission should be one of 3 types')

    # Original submitter
    created_by = models.ForeignKey(User, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True, editable=False)

    # fileset: for revisioning of the submission
    fileset = models.ForeignKey('filestorage.FileSet', null=True, blank=True)

    # frozen: no further revisions allowed
    frozen = models.BooleanField(default=False)

    # FUTURE
    # ------
    # cloned_from = models.ForeignKey('self', null=True, blank=True)
    # vote_for_inclusion_in_scipy [ForeignKey] to ThumbsUpDown model
    # modules_required  [list of modules required to run the code]

    @property
    def last_revision(self):
        try:
            return self.revisions.order_by('-date_created')[0]
        except (KeyError, IndexError):
            return None

    @property
    def num_revisions(self):
        return self.revisions.count()

    @property
    def slug(self):
        try:
            return self.last_revision.slug
        except AttributeError:
            return ''

    def __unicode__(self):
        return self.slug

    def get_absolute_url(self):
        """ I can't seem to find a way to use the "reverse" or "permalink"
        functions to create this URL: do it manually, to match ``urls.py``
        """
        return reverse('spc-view-link', args=[0]).rstrip('0') + \
                '%d/%d/%s' % (self.pk, self.last_revision.rev_id+1, self.slug)


class RevisionManager(models.Manager):
    def create_without_commit(self, **kwargs):
        """
        Uses code from django.db.models.create(...) to create a new instance
        without writing to the database.

        To save the object to the database (presumably after validating it, or
        doing some other checks), you can call the ``obj.save()`` method. E.g.:

            obj = models.Revision.objects.create_without_commit(....)
            ...
            ...
            obj.save(force_insert=True, using=models.Revision.objects.db)
            # or
            obj.save(force_insert=True)
        """
        qs = self.get_query_set()
        obj = qs.model(**kwargs)
        self._for_write = True
        #obj.save(force_insert=True, using=self.db)
        return obj

    def all(self):
        return self.filter(is_displayed=True)

    def absolutely_all(self):
        return super(RevisionManager, self).all()

    def top_authors(self):
        """ From BSD licensed code:
        http://github.com/coleifer/djangosnippets.org/blob/master/cab/models.py
        """
        return User.objects.annotate(score=models.Count('revision'))\
                                               .order_by('-score', 'username')

class Revision(models.Model):

    objects = RevisionManager()

    # The submission: parent item for this revision
    entry = models.ForeignKey(Submission, related_name="revisions")

    # user-provided submission title.
    title = models.CharField(max_length=150,
                        help_text='Provide a <b>title</b> for your submission')

    # auto-created slug field
    slug = models.SlugField(max_length=155, editable=False)

    # Created on
    date_created = models.DateTimeField(auto_now_add=True, editable=False)

    # Users that created this submission
    created_by = models.ForeignKey(User, null=True, blank=True)

    # Submission license. Only used for code packages. Code snippets are
    # always CC0 licensed, and external links must list their own license.
    # There are just too many licenses out there for us to track them all.
    # We don't expect people to be using this site to screen for code based
    # on license. Use Google for that.
    # The only choices right now are CC0 and simplified-BSD.
    sub_license = models.ForeignKey(License, null=True, blank=True,
                verbose_name="Choose a license for your submission")

    # User-provided description of the submission. Uses reStructuredText.
    # Is blank for URL (link) submissions.
    description = models.TextField(help_text=('<b>Explain</b> your '
                    'submission'))

    # HTML version of the ReST ``description`` field
    description_html = models.TextField()

    # User uploaded image
    screenshot = models.ForeignKey('screenshot.Screenshot', null=True,
                                   blank=True)

    # Code snippet hash (will use ssdeep later on: 57 characters)
    hash_id = models.CharField(max_length=60, null=True, blank=True,
                               editable=False)

    # For snippet submissions
    item_code = models.TextField(null=True, blank=True)
    item_highlighted_code = models.TextField(editable=False, null=True,
                                             blank=True)

    # For link-type submissions
    item_url = models.URLField(verbose_name="URL for link-type submssions",
                               blank=True, null=True,
                help_text=("Link to the code's website, documentation, or "
                           'publication (<a target="_blank" href="http://en.'
                           'wikipedia.org/wiki/Digital_object_identifier">'
                           'DOI preferred</a>)'), max_length=255)

    # Tags for this revision
    tags = models.ManyToManyField('tagging.Tag', through='TagCreation')

    # Should this revision be displayed? One might decide to remove
    # revision from display if they violate licenses, or are improper in
    # some way.
    # Also set False for revision by users that submit when not yet
    # authenticated.
    is_displayed = models.BooleanField(default=False)

    # Validation hash
    validation_hash = models.CharField(max_length=40, null=True, blank=True)


    # FUTURE: inspired_by: a comma-separated list of previous submissions
    # FUTURE: list of modules required to run the code

    def __unicode__(self):
        return self.title[0:50] + '::' + str(self.created_by.username)

    @property
    def rev_id(self):
        """ Determines which revision of the submission this is, given the
        ``revision`` object.
        """
        return list(self.entry.revisions.absolutely_all()).index(self)

    @property
    def rev_id_human(self):
        return self.rev_id + 1

    @property
    def human_revision_string(self):
        """ Returns the revision information in a helpful way
        """
        try:
            out = 'Revision %d of %d' % (self.rev_id+1,
                                         self.entry.num_revisions)
        except ValueError:
            out = 'Revision information not available yet'

        return out


    def save(self, *args, **kwargs):
        """ Override the model's saving function to create the slug """
        # http://docs.djangoproject.com/en/dev/topics/db/models/
                                          #overriding-predefined-model-methods
        self.slug = slugify(self.title)

        # Call the "real" save() method.
        super(Revision, self).save(*args, **kwargs)


    def get_absolute_url(self):
        """ I can't seem to find a way to use the "reverse" or "permalink"
        functions to create this URL: do it manually, to match ``urls.py``
        """
        return reverse('spc-view-link', args=[0]).rstrip('0') + \
                        '%d/%d/%s' % (self.entry.pk, self.rev_id+1, self.slug)


class TagCreation(models.Model):
    """
    Tracks by whom and when tags were created
    """
    created_by = models.ForeignKey(User)
    revision = models.ForeignKey(Revision)
    tag = models.ForeignKey('tagging.Tag')
    date_created = models.DateTimeField(auto_now_add=True, editable=False)

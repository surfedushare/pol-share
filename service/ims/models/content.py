import json
import os
from zipfile import ZipFile

from bs4 import BeautifulSoup

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError


class IMSArchive(models.Model):

    file = models.FileField()
    manifest = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def from_file_path(cls, file_path):
        archive = cls()
        archive.file.name = file_path
        archive.clean()
        return archive

    def get_resources(self):
        manifest = BeautifulSoup(self.manifest, "lxml")
        results = {}
        resources = manifest.find_all('resource', identifier=True)
        for resource in resources:
            results[resource['identifier']] = {
                'content_type': resource['type'],
                'main': resource['href'],
                'files': [file['href'] for file in resource.find_all('file')]
            }
        return results

    def get_extract_destination(self):
        tail, head = os.path.split(self.file.name)
        return os.path.join(settings.MEDIA_ROOT, "tmp", head)

    def extract(self):
        destination = self.get_extract_destination()
        if os.path.exists(destination):
            return
        archive = ZipFile(self.file)
        archive.extractall(destination)

    def clean(self):
        archive = ZipFile(self.file)
        try:
            self.manifest = archive.read('imsmanifest.xml')
        except KeyError:
            raise ValidationError('The IMS archive should contain a imsmanifest.xml file')

    def metadata_tag(self):
        return '<pre>{}</pre>'.format(json.dumps(self.get_metadata(), indent=4))
    metadata_tag.short_description = 'Metadata'
    metadata_tag.allow_tags = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.file.name.endswith("imscc"):
            self.__class__ = CommonCartridge
        else:
            self.__class__ = ContentPackage

    def __str__(self):
        tail, head = os.path.split(self.file.name)
        return head

    def get_metadata(self):
        raise NotImplementedError("get_metadata is not available")

    def get_content_tree(self):
        raise NotImplementedError("get_content_tree is not available")


class CommonCartridge(IMSArchive):

    def get_metadata(self):
        manifest = BeautifulSoup(self.manifest, "lxml")
        return {
            'schema': {
                'type': manifest.find('schema').text,
                'version': manifest.find('schemaversion').text
            },
            'title': manifest.find('lomimscc:title').find('lomimscc:string').text,
            'export_at': manifest.find('lomimscc:contribute').find('lomimscc:date').find('lomimscc:datetime').text,
            'license': manifest.find('lomimscc:rights').find('lomimscc:description').find('lomimscc:string').text
        }

    def get_content_tree(self):
        manifest = BeautifulSoup(self.manifest, "lxml")
        return manifest.find('organization').find('item')

    class Meta:
        proxy = True


class ContentPackage(IMSArchive):

    def get_metadata(self):
        manifest = BeautifulSoup(self.manifest, "lxml")
        schema = manifest.find('schema').text
        title = manifest.find('lomcc:title').find('lomcc:string').text if schema == "IMS Common Cartridge" else \
            manifest.find('imsmd:title').find('imsmd:langstring').text
        return {
            'schema': {
                'type': schema,
                'version': manifest.find('schemaversion').text
            },
            'title': title
        }

    def get_content_tree(self):  # TODO: test in pol-harvester
        manifest = BeautifulSoup(self.manifest, "lxml")
        return manifest.find('organization').find_all('item')

    class Meta:
        proxy = True
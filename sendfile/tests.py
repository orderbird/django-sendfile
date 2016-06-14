# coding=utf-8
import os

from django.conf import settings
from django.core.files.storage import Storage
from django.db.models import Field
from django.db.models.fields.files import FieldFile
from django.test import TestCase
from django.http import HttpResponse, Http404, HttpRequest
from django.utils.encoding import smart_str
import os.path
from tempfile import mkdtemp
import shutil
from sendfile import sendfile as real_sendfile, _get_sendfile, is_remote_storage, normalize_filename


def sendfile(request, filename, **kwargs):
    # just a simple response with the filename
    # as content - so we can test without a backend active
    return HttpResponse(filename)


class RemoteStorageMock(Storage):
    # Remote storage has no path only the url parameter

    def url(self, name, headers=None, response_headers=None, expire=None):
        return 'https://bucket.s3.amazonaws.com/media/{}'.format(name)

    def path(self, name):
        raise NotImplementedError


class StorageMock(RemoteStorageMock):
    def path(self, name):
        temp_path = mkdtemp()
        path = os.path.join(temp_path, name)
        open(path, 'w').close()
        return path


class TempFileTestCase(TestCase):
    def setUp(self):
        super(TempFileTestCase, self).setUp()
        self.TEMP_FILE_ROOT = mkdtemp()

    def tearDown(self):
        super(TempFileTestCase, self).tearDown()
        if os.path.exists(self.TEMP_FILE_ROOT):
            shutil.rmtree(self.TEMP_FILE_ROOT)

    def ensure_file(self, filename):
        path = os.path.join(self.TEMP_FILE_ROOT, filename)
        if not os.path.exists(path):
            open(path, 'w').close()
        return path


class FieldFileTestCase(TempFileTestCase):
    def get_field_file(self, storage=RemoteStorageMock):
        field = Field()
        field.storage = storage()
        return FieldFile(self.ensure_file('test.png'), field, 'test.png')


class TestSendfile(TempFileTestCase):
    def setUp(self):
        super(TestSendfile, self).setUp()
        # set ourselves to be the sendfile backend
        settings.SENDFILE_BACKEND = 'sendfile.tests'
        _get_sendfile.clear()

    def _get_readme(self):
        return self.ensure_file('testfile.txt')

    def test_404(self):
        try:
            real_sendfile(HttpRequest(), 'fhdsjfhjk.txt')
        except Http404:
            pass

    def test_sendfile(self):
        response = real_sendfile(HttpRequest(), self._get_readme())
        self.assertTrue(response is not None)
        self.assertEqual('text/plain', response['Content-Type'])
        self.assertEqual(self._get_readme(), smart_str(response.content))

    def test_set_mimetype(self):
        response = real_sendfile(HttpRequest(), self._get_readme(), mimetype='text/plain')
        self.assertTrue(response is not None)
        self.assertEqual('text/plain', response['Content-Type'])

    def test_set_encoding(self):
        response = real_sendfile(HttpRequest(), self._get_readme(), encoding='utf8')
        self.assertTrue(response is not None)
        self.assertEqual('utf8', response['Content-Encoding'])

    def test_attachment(self):
        response = real_sendfile(HttpRequest(), self._get_readme(), attachment=True)
        self.assertTrue(response is not None)
        self.assertEqual('attachment; filename="testfile.txt"', response['Content-Disposition'])

    def test_attachment_filename_false(self):
        response = real_sendfile(HttpRequest(), self._get_readme(), attachment=True, attachment_filename=False)
        self.assertTrue(response is not None)
        self.assertEqual('attachment', response['Content-Disposition'])

    def test_attachment_filename(self):
        response = real_sendfile(HttpRequest(), self._get_readme(), attachment=True, attachment_filename='tests.txt')
        self.assertTrue(response is not None)
        self.assertEqual('attachment; filename="tests.txt"', response['Content-Disposition'])

    def test_attachment_filename_unicode(self):
        response = real_sendfile(HttpRequest(), self._get_readme(), attachment=True, attachment_filename='test’s.txt')
        self.assertTrue(response is not None)
        self.assertEqual('attachment; filename="tests.txt"; filename*=UTF-8\'\'test%E2%80%99s.txt',
                         response['Content-Disposition'])


class TestXSendfileBackend(TempFileTestCase):
    def setUp(self):
        super(TestXSendfileBackend, self).setUp()
        settings.SENDFILE_BACKEND = 'sendfile.backends.xsendfile'
        _get_sendfile.clear()

    def test_correct_file_in_xsendfile_header(self):
        filepath = self.ensure_file('readme.txt')
        response = real_sendfile(HttpRequest(), filepath)
        self.assertTrue(response is not None)
        self.assertEqual(filepath, response['X-Sendfile'])

    def test_xsendfile_header_containing_unicode(self):
        filepath = self.ensure_file(u'péter_là_gueule.txt')
        response = real_sendfile(HttpRequest(), filepath)
        self.assertTrue(response is not None)
        self.assertEqual(smart_str(filepath), response['X-Sendfile'])


class TestNginxBackend(TempFileTestCase):
    def setUp(self):
        super(TestNginxBackend, self).setUp()
        settings.SENDFILE_BACKEND = 'sendfile.backends.nginx'
        settings.SENDFILE_ROOT = self.TEMP_FILE_ROOT
        settings.SENDFILE_URL = '/private'
        _get_sendfile.clear()

    def test_correct_url_in_xaccelredirect_header(self):
        filepath = self.ensure_file('readme.txt')
        response = real_sendfile(HttpRequest(), filepath)
        self.assertTrue(response is not None)
        self.assertEqual('/private/readme.txt', response['X-Accel-Redirect'])

    def test_xaccelredirect_header_containing_unicode(self):
        filepath = self.ensure_file(u'péter_là_gueule.txt')
        response = real_sendfile(HttpRequest(), filepath)
        self.assertTrue(response is not None)
        self.assertEqual(u'/private/péter_là_gueule.txt'.encode('utf-8'), response['X-Accel-Redirect'])


class TestNormalizeFilename(FieldFileTestCase):
    def test_string_does_not_change(self):
        self.assertEqual('', normalize_filename(''))
        self.assertEqual('foobar', normalize_filename('foobar'))

    def test_field_file_with_url(self):
        filename = normalize_filename(self.get_field_file())
        self.assertEqual(filename, 'https://bucket.s3.amazonaws.com/media/test.png')

    def test_field_file_with_path(self):
        filename = normalize_filename(self.get_field_file(storage=StorageMock))
        self.assertIn('test.png', filename)


class TestRemoteStorage(FieldFileTestCase):
    def setUp(self):
        super(TestRemoteStorage, self).setUp()
        settings.SENDFILE_BACKEND = 'sendfile.backends.nginx'
        settings.SENDFILE_ROOT = self.TEMP_FILE_ROOT
        settings.SENDFILE_URL = '/private'
        _get_sendfile.clear()

    def _get_readme(self):
        return self.ensure_file('testfile.txt')

    def test_existing_file_is_not_remote_storage(self):
        existing_file_path = self._get_readme()
        self.assertFalse(is_remote_storage(existing_file_path))

    def test_nonexisting_file_is_not_remote_storage(self):
        self.assertFalse(is_remote_storage(''))
        self.assertFalse(is_remote_storage('not_existing_file.txt'))

    def test_url_is_remote_storage(self):
        url = 'https://bucket.s3.amazonaws.com/media/test.png'
        self.assertTrue(is_remote_storage(url))

    def test_field_file_is_remote_storage(self):
        field_file = self.get_field_file()
        self.assertTrue(is_remote_storage(normalize_filename(field_file)))

    def test_field_file_is_not_remote_storage(self):
        field_file = self.get_field_file(storage=StorageMock)
        self.assertFalse(is_remote_storage(normalize_filename(field_file)))

    def test_send_url_with_nginx_backend(self):
        response = real_sendfile(HttpRequest(), 'https://bucket.s3.amazonaws.com/media/test.png')
        self.assertTrue(response is not None)
        self.assertEqual('/private/https://bucket.s3.amazonaws.com/media/test.png', response['X-Accel-Redirect'])

    def test_send_field_file_wirh_url_with_nginx_backend(self):
        field_file = self.get_field_file()
        response = real_sendfile(HttpRequest(), field_file)
        self.assertTrue(response is not None)
        self.assertEqual('/private/https://bucket.s3.amazonaws.com/media/test.png', response['X-Accel-Redirect'])

    def test_send_field_file_with_path_with_nginx_backend(self):
        field_file = self.get_field_file(storage=StorageMock)
        response = real_sendfile(HttpRequest(), field_file)
        self.assertTrue(response is not None)
        self.assertIn('test.png', response['X-Accel-Redirect'])

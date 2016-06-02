from __future__ import absolute_import

from django.http import HttpResponse

from ._internalredirect import _convert_file_to_url


def sendfile(request, filename, **kwargs):
    remote_storage = kwargs.get('remote_storage', False)
    response = HttpResponse()
    url = _convert_file_to_url(filename, remote_storage)
    response['X-Accel-Redirect'] = url.encode('utf-8')

    return response

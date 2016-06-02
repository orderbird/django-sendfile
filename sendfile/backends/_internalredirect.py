from django.conf import settings
import os.path


def _convert_file_to_url(filename, remote_storage=False):
    url = [settings.SENDFILE_URL]

    if remote_storage:
        url.insert(1, filename)
    else:
        relpath = os.path.relpath(filename, settings.SENDFILE_ROOT)
        while relpath:
            relpath, head = os.path.split(relpath)
            url.insert(1, head)

    return u'/'.join(url)

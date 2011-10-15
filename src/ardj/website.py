import glob
import os

import ardj.settings
import ardj.util


def update(task_name=None):
    """Updates the web site.

    Goes to the directory, specified in website/root_dir, and runs make in it.
    If task_name is not specified, it's read from website/make_task, or
    "autoupdate" is used."""
    dirname = ardj.settings.getpath('website/root_dir', '~/.config/ardj/website')
    if os.path.exists(dirname):
        if task_name is None:
            task_name = ardj.settings.get('website/make_task', 'autoupdate')

        return ardj.util.run(['make', '-C', dirname, task_name])
    print 'Web site not updated: %s does not exist.' % dirname
    return False


def load_page(filename):
    head, text = open(filename, 'rb').read().decode('utf-8').split('---\n', 1)
    page = dict([[x.strip() for x in l.strip().split(':', 1)] for l in head.split('\n') if l.strip()])
    page['text'] = text
    return page


def filename_to_url(filename):
    base_url = ardj.settings.get('website/base_url', 'http://example.com/')

    prefix = os.path.join(ardj.settings.getpath('website/root_dir'), 'input')
    if not filename.startswith(prefix):
        return base_url

    url = base_url.rstrip('/') + '/' + filename[len(prefix) + 1:]
    if url.endswith('.md'):
        url = url[:-3] + '.html'
    if url.endswith('/index.html'):
        url = url[:-10]
    return url


def add_page(pattern, data):
    max_id = 0
    root_dir = ardj.settings.getpath('website/root_dir')

    for filename in glob.glob(os.path.join(root_dir, 'input', pattern)):
        parts = filename.split(os.path.sep)
        if parts[-2].isdigit():
            max_id = max(max_id, int(parts[-2]))

    filename = os.path.join(root_dir, 'input', pattern).replace('*', str(max_id + 1))

    dirname = os.path.dirname(filename)
    if not os.path.exists(dirname):
        os.makedirs(dirname)

    f = open(filename, 'wb')
    for k, v in data.items():
        if k != 'text':
            line = u'%s: %s\n' % (k, v)
            f.write(line.encode('utf-8'))
    f.write('---\n' + data['text'].encode('utf-8'))
    f.close()

    return filename_to_url(filename)

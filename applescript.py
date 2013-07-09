import os
import platform
import sublime
import sublime_plugin
import tempfile
from threading import Thread

from .edit import Edit
from .util import popen

decompile_script = r'''
import sys
from Foundation import NSAppleScript, NSURL

def decompile(path):
    url = NSURL.fileURLWithPath_(path)
    script, errors = NSAppleScript.alloc().initWithContentsOfURL_error_(url, None)
    return script.source()

if __name__ == '__main__':
    path = sys.argv[1]
    sys.stdout.write(decompile(path).replace('\r', '\n').encode('utf8'))
'''

find_app_script = r'''
import LaunchServices
import sys
code, ref, url = LaunchServices.LSFindApplicationForInfo(
    LaunchServices.kLSUnknownCreator, None, sys.argv[1], None, None)
if url:
    sys.stdout.write(url.path().encode('utf8'))
'''


temp_prefix = tempfile.mkdtemp()


def get_tell_target(view):
    APP_NAME_SEL = 'string.quoted.double.application-name.applescript'
    TELL_BLOCK_SEL = 'meta.block.tell.application'
    sel = view.sel()[0].b
    for region in view.find_by_selector(TELL_BLOCK_SEL):
        if region.contains(sel):
            for name_r in view.find_by_selector(APP_NAME_SEL):
                if region.contains(name_r):
                    return view.substr(name_r)


app_name_cache = {}
def find_app(name):
    if not name in app_name_cache:
        app = popen('/usr/bin/python', '-c', find_app_script, name)
        app_name_cache[name] = app
    return app_name_cache[name]


def execute_applescript(source):
    f = tempfile.NamedTemporaryFile(suffix='.applescript', delete=True)
    f.write(source.encode('utf8'))
    f.flush()
    out = popen('/usr/bin/osascript', f.name)
    if out:
        print('AppleScript result:', out)
    f.close()


def launch_scripting_dictionary(app):
    sdef_name = os.path.basename(app).rsplit('.', 1)[0] + '.sdef'
    sdef_path = os.path.join(temp_prefix, sdef_name)
    if not os.path.exists(sdef_path):
        sdef = popen('sdef', app)
        with open(sdef_path, 'w', encoding='utf-8') as f:
            f.write(sdef)

    popen('open', '-a', 'AppleScript Editor', sdef_path)


class ScriptLoader(sublime_plugin.EventListener):
    LOADING = ('\n' * 3) + (' ' * 10) + 'Loading...' + ('\n' * 3)

    def on_load_async(self, view):
        file_name = view.file_name()
        if file_name.endswith('.scpt'):
            settings = view.settings()
            settings.set('scpt-scratch', True)
            view.set_scratch(True)

            with Edit(view) as edit:
                edit.replace(sublime.Region(0, view.size()), self.LOADING)

            code = popen('/usr/bin/python', '-c', decompile_script, file_name)
            if not code.strip():
                return

            proxy = os.path.join(temp_prefix, os.path.basename(file_name))
            with open(proxy, 'w', encoding='utf-8') as f:
                f.write(code)

            view.retarget(proxy)
            view.set_encoding('utf-8')
            settings.set('applescript-proxy', file_name)
            settings.set('syntax', 'Packages/AppleScript/AppleScript.tmLanguage')
            view.run_command('revert')

    def on_modified_async(self, view):
        settings = view.settings()
        if settings.get('applescript-scratch'):
            settings.erase('applescript-scratch')
            view.set_scratch(False)

    def on_post_save_async(self, view):
        settings = view.settings()
        proxy = settings.get('applescript-proxy')
        if proxy:
            popen('osacompile', '-o', proxy, view.file_name())
            return


class AppleScriptCommand:
    def is_enabled(self):
        if platform.system() != 'Darwin':
            return False

        syntax = self.window.active_view().settings().get('syntax')
        return 'AppleScript' in syntax


class run_applescript(sublime_plugin.WindowCommand, AppleScriptCommand):
    def run(self):
        view = self.window.active_view()
        code = view.substr(sublime.Region(0, view.size()))
        Thread(target=execute_applescript, args=(code,)).start()


class open_scripting_dictionary(sublime_plugin.WindowCommand, AppleScriptCommand):
    def run(self):
        view = self.window.active_view()
        name = get_tell_target(view).strip('"') + '.app'
        if name:
            Thread(target=self.spawn, args=(name,)).start()

    def spawn(self, name):
        app = find_app(name)
        if app:
            launch_scripting_dictionary(app)

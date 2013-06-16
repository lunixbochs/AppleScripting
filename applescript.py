import os
import platform
import sublime
import sublime_plugin
import tempfile

from .edit import Edit
from .util import popen

decompile = r'''
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


temp_prefix = tempfile.mkdtemp()


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

            code = popen('/usr/bin/python', '-c', decompile, file_name)
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


class run_applescript(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        code = view.substr(sublime.Region(0, view.size()))
        f = tempfile.NamedTemporaryFile(suffix='.applescript', delete=True)
        f.write(code.encode('utf8'))
        f.flush()
        out = popen('/usr/bin/osascript', f.name)
        if out:
            print('AppleScript result:', out)
        f.close()

    def is_enabled(self):
        if platform.system() != 'Darwin':
            return False

        syntax = self.window.active_view().settings().get('syntax')
        return 'AppleScript' in syntax

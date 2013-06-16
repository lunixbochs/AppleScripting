import subprocess


def clean_output(args):
    return '\n'.join([a.decode('utf8') for a in args if a])


def popen(*cmd):
    p = subprocess.Popen(cmd,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return clean_output(p.communicate())

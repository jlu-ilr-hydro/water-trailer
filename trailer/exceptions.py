'''
Created on 15.06.2015

@author: kraft-p
'''
import time


class TrailerLoggable(object):

    def __init__(self, level, owner=None):
        self.level = level
        self.time = time.time()
        self.owner = owner


class TrailerException(Exception, TrailerLoggable):

    def __init__(self, msg, level, owner=None):
        Exception.__init__(self, msg)
        TrailerLoggable.__init__(self, level)
        self.message = msg

    def __str__(self):
        strtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.time))
        owner = '({})'.format(self.owner) if self.owner else ''
        return '{ty}{o} {t}: {msg}'.format(t=strtime,
                                           ty=type(self).__qualname__,
                                           o=owner,
                                           msg=', '.join(self.args))


class TrailerError(TrailerException):

    def __init__(self, msg, owner=None):
        TrailerException.__init__(self, msg, level=2, owner=owner)


class TrailerWarning(TrailerException):

    def __init__(self, msg, owner=None):
        TrailerException.__init__(self, msg, level=3, owner=owner)


class TrailerInfo(TrailerLoggable):

    def __init__(self, msg, owner=None):
        TrailerLoggable.__init__(self, level=4, owner=owner)
        self.message = msg


class TrailerLog(TrailerLoggable):

    def __init__(self, msg, owner=None):
        super().__init__(level=5, owner=owner)
        self.message = msg


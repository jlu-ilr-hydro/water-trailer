import cherrypy
import datetime
import time
import os, re, yaml
from orderedattrdict import AttrDict

from . import mimetype, mime
from .. import db, home
from ..logger.db import LoggerSource, LoggerValue
postonly = cherrypy.tools.allow(methods=['POST'])  # @UndefinedVariable

def html(obj):
    if hasattr(obj, '__html__'):
        return obj.__html__()
    else:
        return str(obj)


class Yamledit(object):
    exposed = True

    def __init__(self):
        self.currentpath = None

    @cherrypy.expose
    def index(self):
        return (home / 'web/html/yaml.html').read_text(encoding='utf-8')

    @cherrypy.expose
    def f(self, path):
        if type(path).__name__ == "str":
            if (home / 'preferences' / path).exists():
                self.currentpath = path
                return (home / 'web/html/yaml.html').read_text(encoding='utf-8')
            else:
                self.currentpath = None
                raise cherrypy.HTTPRedirect("/yamleditor")
        else:
            self.currentpath = None
            raise cherrypy.HTTPRedirect("/yamleditor")


    @cherrypy.expose
    @mimetype(mime.json)
    def availableyamlfiles(self, **kwargs):
        yamldir = str((home / 'preferences'))
        back=[]
        for file in os.listdir(yamldir):
            if file.endswith(".yaml"):
                if file != "standart.yaml":
                    back.append(file)
        return db.as_json(back)

    @cherrypy.expose
    @mimetype(mime.json)
    def getcontent(self,path):
        if path != None:
            return db.as_json({"content": (home / 'preferences' / path).read_text(encoding='utf-8')})
        else:
            raise FileNotFoundError("Sorry you set no file and got redirected to here. Please set a file in your uri by yamleditor/f/name")

    @cherrypy.expose
    @mimetype(mime.json)
    def getnowpath(self):
        return db.as_json({"path": self.currentpath})

    @cherrypy.expose
    @mimetype(mime.json)
    def savecontent(self, path, content):
        parsed_content = content
        try:
            valid = self.validateYaml(yaml.load(parsed_content))
            if not valid:
                message="""The synatx is correct but you missed some needed parameters"""
            else:
                message=""
            (home / 'preferences' / path).write_text(parsed_content, encoding='utf-8')
            return db.as_json({"success":valid,"message":message})
        except Exception as e:
            return db.as_json({"success":False,"message":str(e)})

    def validateYaml(self,content):
        standart_config_for_yaml = 'standart.yaml'
        stand_content = yaml.load((home / 'preferences' / standart_config_for_yaml).read_text(encoding='utf-8'))

        st_keys = list(set(self.walk_dict(stand_content)))
        co_keys = list(set(self.walk_dict(content)))

        all_fine = True
        for i in st_keys:
            if not co_keys.__contains__(i):
                all_fine = False
                break
        return all_fine

    def walk_dict(self,d):
        all_keys = []
        for k,v in sorted(d.items(),key=lambda x: x[0]):
            if isinstance(v, dict):
                all_keys.append(k)
                tmp_back = self.walk_dict(v)
                for i in tmp_back:
                    all_keys.append(i)
                # or just append the whole key
            else:
                all_keys.append(k)
        return all_keys
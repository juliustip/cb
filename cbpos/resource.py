import os

import cbpos
logger = cbpos.get_logger(__name__)

class Resource(object):
    
    def add(self, name):
        return setattr(self, name, ResourceGetter(name))

class ResourceGetter(object):
    def __init__(self, name):
        self.name = name
    
    def __call__(self, path):
        import pkg_resources
        p = os.path.join('res', path.strip('/'))
        return pkg_resources.resource_filename('cbpos.mod.'+self.name, p)

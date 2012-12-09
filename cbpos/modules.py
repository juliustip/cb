import sys, os
import pkgutil, importlib

import logging
logger = logging.getLogger(__name__)

import cbpos

cbpos.config.set_default('mod', 'disabled_modules', '')
cbpos.config.set_default('mod', 'modules_path', './cbpos/mod')

class BaseModuleLoader(object):
    """
    Abstract module loader from which all modules should have a subclass.
    Defines common actions that should take place when loading a module.
    """
    name = None
    dependencies = set()
    config = []
    version = 0
    
    def __init__(self, base_name):
        self.base_name = base_name
        if self.name is None:
            self.name = self.base_name.title()
        
        self.dependencies = set(self.dependencies)
        
        for section, options in self.config:
            for opt, val in options.iteritems():
                cbpos.config.set_default(section, opt, val)
    
    def ui_handler(self):
        """
        Defines a UI handler, an object responsible for setting up the UI and running it.
        It should allow modules to interact with it.
        Based on the configuration, the UI handler of the chosen module will be
        assigned to cbpos.ui when loading the modules.  
        """
        return None
    
    def load(self):
        """
        Loads the database models.
        """
        return []
    
    def test(self):
        """
        Adds dummy information to the database for test and demo purposes.
        """
        pass
    
    def menu(self):
        """
        Returns the menu structure [Roots, Children] Items corresponding to this module.
        """
        return [[], []]
    
    def argparser(self):
        """
        Parse the command line arguments.
        """
        pass
    
    def init(self):
        """
        Perform arbitrary initial tasks.
        Do NOT insert UI related code here.
        Connect to the appropriate dispatcher signals here instead.
        """
        return True
    
    def __lt__(self, mod):
        """
        Implements the '<' comparison operator.
        Used when sorting the list of modules by dependencies.
        """
        return (self.base_name in mod.dependencies)
    
    def __repr__(self):
        return '<ModuleLoader %s>' % (self.base_name,)

class ModuleWrapper(object):
    """
    Wrapper around the actual installed module.
    Provides convenience functions for common tasks.
    """
    def __init__(self, package):
        self.package = package
        self.name = package[1]
        
        self.loader = None
        self.disabled = False
        self.missing_dependency = False
        
        global modules
        modules[self.name] = self

    def load(self):
        """
        Load the module's package and initialize the ModuleLoader class. 
        """
        if self.disabled:
            return False
        self.top_module = importlib.import_module('cbpos.mod.'+self.name)
        if self.top_module is None:
            self.loader = None
            return False
        try:
            self.loader = self.top_module.ModuleLoader(self.name)
        except AttributeError:
            self.loader = None
            return False
        print len(dir(self.loader))
        return True
    
    def disable(self, missing_dependency=False):
        """
        Mark the module as disabled, specifying if it is conflicting with a missing dependency.
        """
        if self.disabled:
            return
        self.disabled = True
        self.missing_dependency = missing_dependency
        sys.modules['cbpos.mod.'+self.name] = None
    
    @property
    def res_path(self):
        """
        Return the path to the module's resources.
        Only to be used when working with the modules themselves.
        Otherwise, use `cbpos.res.NAME('/path/to/resource')`.  
        """
        return getattr(cbpos.res, self.name)('')
    
    @property
    def path(self):
        if self.top_module is None:
            return None
        else:
            return os.path.dirname(self.top_module.__file__)
    
    def __lt__(self, other):
        """
        Implements the '<' comparison operator.
        Used when sorting the list of modules by dependencies.
        """
        return self.loader is not None and other.loader is not None and self.loader<other.loader
    
    def __repr__(self):
        return '<ModuleWrapper %s>' % (self.name,)

modules = {}
missing = set()

def init():
    """
    Load all modules, taking care of disabled and conflicting ones.
    """
    # Extract names of disabled modules from config
    disabled_str = cbpos.config['mod', 'disabled_modules']
    disabled_names = disabled_str.split(',') if disabled_str != '' else []
    
    logger.debug('Loading modules...')
    
    #modules_path = [os.path.abspath(path) for path in cbpos.config['mod', 'modules_path'].split(':')]
    #if len(modules_path) == 1 and modules_path[0] == '':
    #    modules_path = os.path.dirname(__file__)
    # Package with names starting with '_' are ignored
    packages = [p for p in pkgutil.walk_packages(path()) if not p[1].startswith('_') and p[2]]
    
    for pkg in packages:
        mod = ModuleWrapper(pkg)
        if mod.name in disabled_names:
            logger.debug('Module %s is disabled.' % (mod.name,))
            mod.disable()
            continue
        logger.debug('Loading module %s...' % (mod.name,))
        if not mod.load():
            logger.warn('Invalid module %s' % (mod.name,))
    logger.debug('(%d) modules found: %s' % (len(modules), ', '.join(m.name for m in all_modules())))
    
    disabled = list(disabled_modules()) 
    if len(disabled) > 0:
        logger.debug('(%d) modules disabled: %s' % (len(disabled), ', '.join(m.name for m in disabled)))
    
    check_dependencies()
    
    if len(missing) > 0:
        logger.warn('(%d) modules disabled for missing dependencies: %s' % (len(missing), ', '.join(name for name in missing)))

def check_dependencies():
    logger.debug('Checking module dependencies...')
    conflict = set()
    missing = set()
    module_names = set(k for k, m in modules.iteritems() if not m.disabled)
    for m in enabled_modules():
        diff = m.loader.dependencies-module_names
        if diff:
            logger.warn('Missing dependencies for module %s: %s' % (m.name, ', '.join(diff)))
            conflict.add(m)
            missing.update(diff)
    
    def all_conflicted(con):
        for m1 in con:
            yield m1
            for m2 in all_conflicted(set(m for m in enabled_modules() if m1.name in m.loader.dependencies)):
                yield m2
    
    for m in all_conflicted(conflict):
        m.disable(missing_dependency=True)

def depsort(ls):
    """
    Sorts modules such that no module comes before its dependencies in the list.
    Note: it will fail to do so when circular dependencies between modules are present.
    """
    sorted_ls = []
    for m1 in ls:
        for i, m2 in enumerate(sorted_ls[:]):
            if m1<m2:
                sorted_ls.insert(i, m1)
                break
        else:
            sorted_ls.append(m1)
    return sorted_ls

# Helper functions

def path():
    return [os.path.abspath(path) for path in cbpos.config['mod', 'modules_path'].split(':')]

def is_installed(module_name):
    return module_name in modules

def is_enabled(module_name):
    return is_installed(module_name) and not modules[module_name].disabled

def all_modules():
    return depsort(modules.itervalues())

def by_name(module_name):
    return modules[module_name]

def disabled_modules():
    return depsort(m for m in modules.itervalues() if m.disabled)

def enabled_modules():
    return depsort(m for m in modules.itervalues() if not m.disabled)

def all_loaders():
    return depsort(m.loader for m in modules.itervalues() if not m.disabled)

# TRANSLATORS

def init_translators(tr_builder):
    for mod in all_loaders():
        tr_builder.add(mod.base_name)

def init_resources(res):
    for mod in all_loaders():
        res.add(mod.base_name)

# ARGUMENT PARSERS
def parse_args():
    for mod in all_loaders():
        logger.debug('Parsing command-line arguments for %s' % (mod.base_name,))
        mod.argparser()

# DATABASE EXTENSION

def load_database():
    """
    Load all the database models of every module so that they can be used with SQLAlchemy.
    """
    for mod in all_loaders():
        logger.debug('Loading DB models for %s' % (mod.base_name,))
        models = mod.load()
        logger.debug('%d found.' % (len(models),))

def config_database():
    """
    Clear and recreate the whole database.
    Note: Only the tables are changed, the database itself cannot be created or dropped.
    """
    logger.debug('Clearing database...')
    cbpos.database.clear()
    logger.debug('Creating database...')
    cbpos.database.create()

def config_test_database():
    """
    Insert the test database values of every module installed.
    """
    logger.debug('Adding test values to database...')
    for mod in all_loaders():
        logger.debug('Adding test values for %s' % (mod.base_name,))
        mod.test()

# MENU EXTENSION

def extend_menu(menu):
    """
    Load all menu extensions of every module, meaning all the root items and sub-items defined.
    """
    from cbpos.menu import MenuRoot, MenuItem
    roots = []
    items = []
    for mod in all_loaders():
        logger.debug('Loading menu for %s...' % (mod.base_name,))
        mod_roots, mod_items = mod.menu()
        roots.extend(mod_roots)
        items.extend(mod_items)

    for root in roots:
        MenuRoot(menu, **root)

    for item in items:
        MenuItem(menu, **item)
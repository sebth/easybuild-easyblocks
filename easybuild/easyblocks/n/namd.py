##
# This file is an EasyBuild reciPY as per https://github.com/hpcugent/easybuild
#
# Copyright:: Copyright 2013-2014 CaSToRC, The Cyprus Institute
# Authors::   George Tsouloupas <g.tsouloupas@cyi.ac.cy>
# License::   MIT/GPL
# $Id$
#
##
"""
Easybuild support for building NAMD, implemented as an easyblock

@author: George Tsouloupas (Cyprus Institute)
@author: Kenneth Hoste (Ghent University)
"""
import glob
import os
import shutil
from distutils.version import LooseVersion

import easybuild.tools.toolchain as toolchain
from easybuild.easyblocks.generic.makecp import MakeCp
from easybuild.framework.easyconfig import CUSTOM
from easybuild.tools.filetools import extract_file, run_cmd
from easybuild.tools.modules import get_software_root, get_software_version


class EB_NAMD(MakeCp):
    """
    Support for building NAMD
    """
    @staticmethod
    def extra_options():
        """Define extra NAMD-specific easyconfig parameters."""
        extra_vars = [
            # see http://charm.cs.illinois.edu/manuals/html/charm++/A.html
            ('charm_arch', ['net-linux-x86_64 ibverbs', "Charm++ target architecture", CUSTOM]),
            ('charm_opts', ['--with-production', "Charm++ build options", CUSTOM]),
            ('namd_basearch', ['Linux-x86_64', "NAMD base target architecture (compiler family is appended", CUSTOM]),
            ('namd_cfg_opts', ['', "NAMD configure options", CUSTOM]),
        ]
        extra = dict(MakeCp.extra_options(extra_vars=extra_vars))
        # files_to_copy is useless here, and definitely not mandatory, so get rid of it
        del extra['files_to_copy']
        return extra.items()

    def __init__(self,*args,**kwargs):
        """Custom easyblock constructor for NAMD, initialize class variables."""
        super(EB_NAMD, self).__init__(*args, **kwargs)
        self.namd_arch = None

    def configure_step(self):
        """Custom configure step for NAMD, we build charm++ first (if required)."""

        # complete Charm ++ and NAMD architecture string with compiler family
        comp_fam = self.toolchain.comp_family()
        namd_comp = None
        if comp_fam in [toolchain.INTELCOMP]:  #@undefinedvariable
            if self.toolchain.options['32bit']:
                # Intel compilers, 32-bit
                self.cfg.update('charm_arch', "icc")
            else:
                # Intel compilers, 64-bit
                self.cfg.update('charm_arch', "icc8")
            namd_comp = 'icc'

        elif comp_fam in [toolchain.GCC]:  #@UndefinedVariable
            self.cfg.update('charm_arch', "gcc")
            namd_comp = 'g++'
        else:
            self.log.error("Unknown compiler family, can't complete NAMD target architecture.")

        self.log.info("Updated 'charm_arch': %s" % self.cfg['charm_arch'])
        self.namd_arch = '%s-%s' % (self.cfg['namd_basearch'], namd_comp)
        self.log.info("Completed NAMD target architecture: %s" % self.namd_arch)

        charm_tarballs = glob.glob('charm-*.tar')
        if len(charm_tarballs) != 1:
            self.log.error("Expected to find exactly one tarball for Charm++, found: %s" % charm_tarballs)

        extract_file(charm_tarballs[0], os.getcwd())

        cmd = "./build charm++ %s %s -j%s" % (self.cfg['charm_arch'], self.cfg['charm_opts'], self.cfg['parallel'])
        charm_subdir = '.'.join(os.path.basename(charm_tarballs[0]).split('.')[:-1])
        self.log.debug("Building Charm++ using cmd '%s' in '%s'" % (cmd, charm_subdir))
        run_cmd(cmd, path=charm_subdir)

        # NAMD dependencies: CUDA, FFTW
        cuda = get_software_version('CUDA')
        if cuda:
            self.cfg.update('namd_cfg_opts', "--with-cuda --cuda-prefix %s" % cuda)

        fftw = get_software_root('FFTW')
        if fftw:
            if LooseVersion(get_software_version('FFTW')) >= LooseVersion('3.0'):
                self.cfg.update('namd_cfg_opts', "--with-fftw3")
            else:
                self.cfg.update('namd_cfg_opts', "--with-fftw")
            self.cfg.update('namd_cfg_opts', "--fftw-prefix %s" % fftw)

        namd_charm_arch = "--charm-arch %s" % '-'.join(self.cfg['charm_arch'].strip().split(' '))
        cmd = "./config %s %s %s " % (self.namd_arch, namd_charm_arch, self.cfg["namd_cfg_opts"])
        run_cmd(cmd)

    def build_step(self):
        """Build NAMD for configured architecture"""
        super(EB_NAMD, self).build_step(path=self.namd_arch)

    def install_step(self):
        """Install by copying the correct directory to the install dir"""
        srcdir = os.path.join(self.cfg['start_dir'], self.namd_arch)
        try:
            # copy all files, except for .rootdir (required to avoid cyclic copying)
            for item in [x for x in os.listdir(srcdir) if not x in ['.rootdir']]:
                fullsrc = os.path.join(srcdir, item)
                if os.path.isdir(fullsrc):
                    shutil.copytree(fullsrc, os.path.join(self.installdir, item), symlinks=False)
                elif os.path.isfile(fullsrc):
                    shutil.copy2(fullsrc, self.installdir)
        except OSError, err:
            self.log.error("Failed to copy NAMD build from %s to install directory: %s" % (srcdir, err))

    def make_module_extra(self):
        """Add the install directory to PATH"""
        txt = super(EB_NAMD, self).make_module_extra()
        txt += self.moduleGenerator.prepend_paths("PATH", [''])
        return txt

    def sanity_check_step(self):
        """Custom sanity check for NAMD."""
        custom_paths = {
            'files': ['charmrun', 'flipbinpdb', 'flipdcd', 'namd2', 'psfgen'],
            'dirs': ['inc'],
        }
        super(EB_NAMD, self).sanity_check_step(custom_paths=custom_paths)

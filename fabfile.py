import os
from fabric.api import env, task
from fabtools import require
import config


env.hosts = config.HOSTS
env.user = config.USER or env.user


@task
def install():
    install_dependencies()

    require.user(config.GIS_USER, create_home=False, shell='/bin/false')
    require.directory('/opt/osm', owner=config.GIS_USER, use_sudo=True)


@task
def install_dependencies():
    if os.path.exists('sources'):
        with open('sources') as f:
            source_list = []
            ppa_list = []
            for line in f:
                source = line.strip()
                if source:
                    if source.lower().startswith('ppa:'):
                        ppa_list.append(source)
                    else:
                        source_list.append(source)
            for source in source_list:
                require.deb.source(source.split())
            for source in ppa_list:
                require.deb.ppa(source)

    if os.path.exists('packages'):
        with open('packages') as f:
            package_list = []
            for line in f:
                package = line.strip()
                if package:
                    package_list.append(package)
            if package_list:
                require.deb.packages(package_list, update=True)


def create_db():
    pass


def setup_db():
    pass


@task
def fill_db():
    pass

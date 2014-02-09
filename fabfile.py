import os
from fabric.api import env, sudo, task
from fabtools import require, postgres
import config


def _run_as_pg(command):
    return sudo(command, user='postgres')


postgres._run_as_pg = _run_as_pg


env.hosts = config.HOSTS
env.user = config.USER or env.user


@task
def install():
    # swap only when necessary
    require.system.sysctl('vm.swappiness', 0, persist=True)
    # max shared memory in bytes
    require.system.sysctl(
        'kernel.shmmax',
        config.RAM_SIZE / 4 * 1024 * 1024,
        persist=True)

    require.user(config.GIS_USER, create_home=False, shell='/bin/false')
    require.directory('/opt/osm', owner=config.GIS_USER, use_sudo=True)

    install_dependencies()

    setup_postgres()
    setup_db()


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


@task
def setup_postgres(for_import=False):
    context = {
        'shared_buffers': config.RAM_SIZE / 8,
        'maintenance_work_mem': config.RAM_SIZE / (2 if for_import else 8),
        'work_mem': 50,
        'effective_cache_size': config.RAM_SIZE / 4 * 3,
        'synchronous_commit': 'off',
        'checkpoint_segments': config.RAM_SIZE / 320,
        'checkpoint_timeout': 10,
        'checkpoint_completion_target': 0.9,
        'fsync': 'off' if for_import else 'on',
        'full_page_writes': 'off' if for_import else 'on',
    }
    require.files.template_file(
        path='/etc/postgresql/9.1/main/postgresql.conf',
        template_source='templates/postgresql.conf',
        context=context,
        use_sudo=True,
        owner='postgres')
    require.service.restarted('postgresql')


@task
def setup_db():
    require.postgres.user(config.GIS_USER, config.GIS_PASSWORD)
    require.postgres.database(config.GIS_DB, config.GIS_USER)


@task
def fill_db():
    pass

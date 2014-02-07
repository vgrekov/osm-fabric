import os
from fabric.api import env, task
from fabric.operations import reboot, sudo
from fabtools import require, system
import config


env.hosts = config.HOSTS
env.user = config.USER or env.user


@task
def install():
    configured = True
    context = {
        # swap only when necessary
        'vm.swappiness': 0,
        # max shared memory in bytes
        'kernel.shmmax': config.RAM_SIZE / 4 * 1024 * 1024,
    }
    for key in context:
        if str(system.get_sysctl(key)) != str(context[key]):
            configured = False
            break
    if not configured:
        require.files.template_file(
            path='/etc/sysctl.conf',
            template_source='templates/sysctl.conf',
            context=context,
            use_sudo=True,
            owner='root')

        # reboot to apply system settings
        reboot(5 * 60)  # wait 5 mins max

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
def setup_postgres():
    context = {
        'shared_buffers': config.RAM_SIZE / 8,
        'maintenance_work_mem': config.RAM_SIZE / 2,
        'work_mem': 50,
        'effective_cache_size': config.RAM_SIZE / 4 * 3,
        'synchronous_commit': 'off',
        'checkpoint_segments': config.RAM_SIZE / 320,
        'checkpoint_timeout': 10,
        'checkpoint_completion_target': 0.9,
        'fsync': 'off',
        'full_page_writes': 'off',
    }
    require.files.template_file(
        path='/etc/postgresql/9.1/main/postgresql.conf',
        template_source='templates/postgresql.conf',
        context=context,
        use_sudo=True,
        owner='postgres')
    sudo('service postgresql restart')


@task
def setup_db():
    pass


@task
def fill_db():
    pass

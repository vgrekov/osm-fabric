import os
from fabric.api import env, sudo, task
from fabric.context_managers import cd
from fabtools import require, postgres
import config


def _run_as_pg(command):
    return sudo(command, user='postgres')


postgres._run_as_pg = _run_as_pg


env.hosts = config.HOSTS
env.user = config.USER or env.user


pbf = None


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
    setup_postgres_users()

    get_pbf()

    install_nominatim()
    # install_tile_server()


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
    context = {
        'db_name': config.GIS_DB,
        'db_user': config.GIS_USER,
    }
    require.files.template_file(
        path='/etc/postgresql/9.1/main/pg_hba.conf',
        template_source='templates/pg_hba.conf',
        context=context,
        use_sudo=True,
        owner='postgres')
    require.service.restarted('postgresql')


@task
def setup_postgres_users():
    www_user = 'www-data'
    www_user_exists = int(sudo(
        'psql -t -A -c '
        + '''"SELECT COUNT(*) FROM pg_user WHERE usename = '%s'"''' % www_user,
        user='postgres'))
    print 'www_user_exists is ' + str(www_user_exists)
    if not www_user_exists:
        sudo('createuser -SDR "%s"' % www_user, user='postgres')
    require.postgres.user(config.GIS_USER, config.GIS_PASSWORD, superuser=True)


@task
def get_pbf():
    global pbf
    pbf_url = 'http://download.geofabrik.de/'\
        + config.REGION + '-latest.osm.pbf'
    pbf = pbf_url.rpartition('/')[2]
    with cd('/opt/osm'):
        require.file(
            url=pbf_url,
            use_sudo=True,
            owner=config.GIS_USER)


@task
def install_nominatim():
    setup_postgres(for_import=True)
    with cd('/opt/osm'):
        nominatime_archive = 'Nominatim-%s.tar.bz2' % config.NOMINATIM_VERSION
        nominatim_url = 'http://www.nominatim.org/release/'\
            + nominatime_archive
        require.file(
            url=nominatim_url,
            use_sudo=True,
            owner=config.GIS_USER)
        nominatim_dir = sudo(
            '''tar tf %s | sed -e 's@/.*@@' | uniq''' % nominatime_archive,
            user=config.GIS_USER)
        sudo(
            '''tar xvf ''' + nominatime_archive, user=config.GIS_USER)
        with cd(nominatim_dir):
            sudo('./autogen.sh', user=config.GIS_USER)
            sudo('./configure', user=config.GIS_USER)
            sudo('make', user=config.GIS_USER)
            context = {
                'db_name': config.GIS_DB,
                'db_user': config.GIS_USER,
                'db_passowrd': config.GIS_PASSWORD,
            }
            require.files.template_file(
                path='settings/local.php',
                template_source='templates/local.php',
                context=context,
                use_sudo=True,
                owner=config.GIS_USER)
            # with cd('data'):
            #     wiki_urls = [
            #         'http://www.nominatim.org/data/wikipedia_article.sql.bin',
            #         'http://www.nominatim.org/data/wikipedia_redirect.sql.bin'
            #     ]
            #     for url in wiki_urls:
            #         require.file(
            #             url=url,
            #             use_sudo=True,
            #             owner=config.GIS_USER)
            sudo(
                './utils/setup.php --osm-file %s --all --osm2pgsql-cache %d'
                % ('/opt/osm/' + pbf, config.RAM_SIZE / 4 * 3),
                user=config.GIS_USER)
            sudo(
                './utils/specialphrases.php --countries > sp_countries.sql',
                user=config.GIS_USER)
            sudo(
                'psql -d %s -f sp_countries.sql' % config.GIS_DB,
                user=config.GIS_USER)
            sudo(
                './utils/specialphrases.php --wiki-import > sp.sql',
                user=config.GIS_USER)
            sudo(
                'psql -d %s -f sp.sql' % config.GIS_DB,
                user=config.GIS_USER)
            require.directory(
                '/var/www/nominatim',
                mode='755',
                owner=config.GIS_USER,
                use_sudo=True)
            sudo(
                './utils/setup.php --create-website /var/www/nominatim',
                user=config.GIS_USER)
            require.apache.site(
                'nominatim',
                template_source='templates/nominatim.conf')
            require.service.restarted('apache2')
    setup_postgres(for_import=False)


@task
def install_tile_server():
    mapnik_db = 'mapnikdb'
    require.postgres.database(mapnik_db, config.GIS_USER)

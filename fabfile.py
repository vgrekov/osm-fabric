import os
from fabric.api import env, sudo, task
from fabric.context_managers import cd
from fabtools import apache, postgres, require, system
import config


def _run_as_pg(command):
    return sudo(command, user='postgres')
postgres._run_as_pg = _run_as_pg


def _get_config_name(config):
    print '_get_config_name("%s")' % config
    return config
apache._get_config_name = _get_config_name
require.apache._get_config_name = _get_config_name

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

    dependencies()

    pgconfig()
    pgusers()

    pbf()

    nominatim()
    tiles()
    osrm()


@task
def dependencies():
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
def pgconfig(for_import=False):
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
def pgusers():
    www_user = 'www-data'
    www_user_exists = int(sudo(
        '''psql -t -A -c '''
        '''"SELECT COUNT(*) FROM pg_user WHERE usename = '%s'"''' % www_user,
        user='postgres'))
    print 'www_user_exists is ' + str(www_user_exists)
    if not www_user_exists:
        sudo('createuser -SDR "%s"' % www_user, user='postgres')
    require.postgres.user(config.GIS_USER, config.GIS_PASSWORD, superuser=True)


@task
def pbf():
    pbf_url = 'http://download.geofabrik.de/%s-latest.osm.pbf'\
        % config.REGION
    with cd('/opt/osm'):
        require.file(
            url=pbf_url,
            use_sudo=True,
            owner=config.GIS_USER)


@task
def nominatim():
    pgconfig(for_import=True)
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
            with cd('data'):
                wiki_urls = [
                    'http://www.nominatim.org/data/wikipedia_article.sql.bin',
                    'http://www.nominatim.org/data/wikipedia_redirect.sql.bin'
                ]
                for url in wiki_urls:
                    require.file(
                        url=url,
                        use_sudo=True,
                        owner=config.GIS_USER)
            sudo(
                './utils/setup.php --osm-file %s --all --osm2pgsql-cache %d'
                % (pbf_path(), config.RAM_SIZE / 4 * 3),
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
                '200-nominatim.conf',
                template_source='templates/200-nominatim.conf')
            require.service.restarted('apache2')
    pgconfig(for_import=False)


@task
def tiles():
    require.deb.package('libapache2-mod-tile', update=True)

    chown('/var/www/osm', owner='www-data', recursive=True)
    chown('/var/run/renderd/renderd.sock', owner='www-data')
    chown('/var/lib/mod_tile', owner='www-data', recursive=True)

    pgconfig(for_import=True)
    mapnik_db = 'mapnikdb'
    require.postgres.database(mapnik_db, config.GIS_USER)

    sql_scripts = [
        '/usr/share/postgresql/9.1/contrib/postgis-1.5/postgis.sql',
        '/usr/share/postgresql/9.1/contrib/postgis-1.5/spatial_ref_sys.sql',
    ]
    for script in sql_scripts:
        sudo('psql -d %s -f %s' % (mapnik_db, script), user=config.GIS_USER)

    processes = system.cpus()
    cache = config.RAM_SIZE / 4 * 3
    sudo(
        'osm2pgsql --slim --number-processes %d -C %d -d %s %s'
        ' --cache-strategy sparse'
        % (processes, cache, mapnik_db, pbf_path()),
        user=config.GIS_USER)

    tables = [
        'planet_osm_line',
        'planet_osm_point',
        'planet_osm_polygon',
        'planet_osm_roads',
    ]
    tables_args = ' '.join('-t ' + table for table in tables)
    with cd('/opt/osm'):
        sudo(
            'pg_dump -b -o %s %s | gzip > %s.gz'
            % (tables_args, mapnik_db, mapnik_db),
            user=config.GIS_USER)
        sudo(
            'gunzip -c %s.gz | psql %s'
            % (mapnik_db, config.GIS_DB),
            user=config.GIS_USER)

    pgconfig(for_import=False)

    require.file(
        '/var/lib/mod_tile/planet-import-complete',
        use_sudo=True, owner='www-data')

    context = {
        'db_name': config.GIS_DB,
        'db_user': config.GIS_USER,
        'db_password': config.GIS_PASSWORD,
    }
    require.files.template_file(
        '/etc/mapnik-osm-data/inc/datasource-settings.xml.inc',
        template_source='templates/datasource-settings.xml.inc',
        context=context,
        use_sudo=True,
        owner='root')

    require.apache.site_disabled('tileserver_site')
    require.apache.site(
        '100-tileserver_site.conf',
        template_source='templates/100-tileserver_site.conf')

    require.service.restarted('renderd')


@task
def osrm():
    with cd('/opt/osm'):
        pbf_base = pbf_path().partition('.')[0]
        require.git.working_copy(
            'https://github.com/DennisOSRM/Project-OSRM.git',
            'osrm',
            use_sudo=True,
            user=config.GIS_USER)
        require.directory('osrm/build', use_sudo=True, owner=config.GIS_USER)
        with cd('osrm/build'):
            sudo('cmake ..', user=config.GIS_USER)
            sudo('make', user=config.GIS_USER)
            sudo('ln -s ../profiles profiles', user=config.GIS_USER)
            sudo('ln -s ../profile.lua profile.lua', user=config.GIS_USER)
            require.files.template_file(
                '.stxxl',
                template_source='templates/.stxxl',
                context={'disk': '/opt/osm/osrm/build/stxxl'},
                use_sudo=True,
                owner=config.GIS_USER)
            sudo('./osrm-extract %s' % pbf_path(), user=config.GIS_USER)
            sudo('./osrm-prepare %s.osrm' % pbf_base, user=config.GIS_USER)
        context = {
            'threads': system.cpus(),
            'pbf_base': pbf_base,
        }
        require.files.template_file(
            path='osrm-routed.ini',
            template_source='templates/osrm-routed.ini',
            context=context,
            use_sudo=True,
            owner=config.GIS_USER)
    require.files.template_file(
        path='/etc/init.d/osrm-routed',
        template_source='templates/osrm-routed',
        context={'user': config.GIS_USER},
        use_sudo=True,
        owner='root')
    sudo('chmod +x /etc/init.d/osrm-routed')
    sudo('update-rc.d osrm-routed defaults')
    require.service.started('osrm-routed')


def chown(path, owner, group=None, recursive=False):
    context = {
        'path': path,
        'user': owner,
        'group': group or owner,
        'flags': ' -R' if recursive else ''
    }
    sudo('chown%(flags)s %(user)s.%(group)s %(path)s' % context)


def pbf_path():
    return '/opt/osm/%s-latest.osm.pbf' % config.REGION.rpartition('/')[2]

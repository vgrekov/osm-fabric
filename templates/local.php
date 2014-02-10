<?php
	// General settings
	@define('CONST_Debug', false);
	@define('CONST_Database_DSN', 'pgsql://%(db_user)s:%(db_passowrd)s@127.0.0.1/%(db_name)s'); // <driver>://<username>:<password>@<host>:<port>/<database>
	@define('CONST_Max_Word_Frequency', '50000');

	// Paths
	@define('CONST_Osm2pgsql_Binary', CONST_BasePath.'/osm2pgsql/osm2pgsql');
	
	// osm2pgsql settings
	@define('CONST_Osm2pgsql_Flatnode_File', null);

	// Website settings
	@define('CONST_Website_BaseURL', 'http://localhost/nominatim/');
	@define('CONST_Tile_Default', 'Mapnik');

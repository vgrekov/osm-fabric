<!--
Settings for your postgres setup.

Note: feel free to leave password, host, port, or use blank
-->

<Parameter name="type">postgis</Parameter>
<Parameter name="host">127.0.0.1</Parameter>
<Parameter name="dbname">%(db_name)s</Parameter>
<Parameter name="user">%(db_user)s</Parameter>
<Parameter name="password">%(db_password)s</Parameter>
<!-- Parameter name="port"></Parameter -->
<!-- this should be 'false' if you are manually providing the 'extent' -->
<Parameter name="estimate_extent">false</Parameter>
<!-- manually provided extent in epsg 900913 for whole globe -->
<!-- providing this speeds up Mapnik database queries -->
<Parameter name="extent">-20037508,-19929239,20037508,19929239</Parameter>

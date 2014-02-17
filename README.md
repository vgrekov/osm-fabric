osm-fabric
==========


Description
-----------

Fabric script for "fresh" Ubuntu Server 12.04 x64 that installs:
* `Nominatim`
* Tile server stack (`mod_tile`, `renderd`, `mapnik`)
* `OSRM`


Installation
------------

* To be able to run the script you will need `fabric` and `fabtools`:
..* `pip install fabric`
..* `pip install fabtools`
* Create `config.py` based on `config.py.example`
* `fab install`
from __future__ import annotations

from io import BytesIO
import unittest

from scripts.audit_madrid_osm_buildings import summarize_osm_xml


FIXTURE = b'''<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="building-audit-test">
  <node id="1" lat="40.41" lon="-3.70"/>
  <node id="2" lat="40.41" lon="-3.69"/>
  <node id="3" lat="40.42" lon="-3.69"/>
  <node id="4" lat="40.42" lon="-3.70"/>
  <way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="building" v="yes"/><tag k="height" v="12.5 m"/><tag k="min_height" v="2"/>
  </way>
  <way id="11"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="building" v="residential"/><tag k="building:levels" v="4"/>
    <tag k="min_level" v="1"/>
  </way>
  <way id="12"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
    <tag k="building:part" v="yes"/><tag k="height" v="unknown"/>
  </way>
  <way id="13"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="building" v="yes"/>
  </way>
  <relation id="20"><member type="way" ref="10" role="outer"/>
    <tag k="type" v="multipolygon"/><tag k="building" v="apartments"/>
    <tag k="building:levels:aboveground" v="6"/>
  </relation>
</osm>
'''


class MadridBuildingAuditTests(unittest.TestCase):
    def test_counts_observed_heights_levels_and_unknowns_without_converting_them(self) -> None:
        report = summarize_osm_xml(BytesIO(FIXTURE))
        self.assertEqual(report["osm_elements"], {"node": 4, "way": 4, "relation": 1})
        self.assertEqual(report["building_ways"], 4)
        self.assertEqual(report["closed_building_ways"], 3)
        self.assertEqual(report["open_building_ways"], 1)
        self.assertEqual(report["building_relations"], 1)
        self.assertEqual(report["footprint_candidates"], 4)
        self.assertEqual(report["height_values"]["explicit_numeric_height"], 1)
        self.assertEqual(report["height_values"]["levels_only_not_converted_to_meters"], 2)
        self.assertEqual(report["height_values"]["height_tag_unparsed_or_nonpositive"], 1)
        self.assertEqual(report["height_values"]["height_and_levels_unknown"], 0)
        self.assertFalse(report["interpretation"]["levels_were_converted_to_meters"])
        self.assertEqual(sum(report["coverage_percent"].values()), 100.0)

    def test_empty_building_denominator_has_no_fake_zero_coverage(self) -> None:
        report = summarize_osm_xml(BytesIO(b'<osm version="0.6"><node id="1" lat="40" lon="-3"/></osm>'))
        self.assertEqual(report["footprint_candidates"], 0)
        self.assertTrue(all(value is None for value in report["coverage_percent"].values()))


if __name__ == "__main__":
    unittest.main()

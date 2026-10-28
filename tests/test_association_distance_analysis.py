import unittest

from scripts.analyze_h16_h23_association_distances import band


class AssociationDistanceTests(unittest.TestCase):
    def test_bands_have_expected_boundaries(self):
        self.assertEqual(band(0),"0-25");self.assertEqual(band(24.999),"0-25");self.assertEqual(band(25),"25-50");self.assertEqual(band(50),"50-100");self.assertEqual(band(100),"50-100");self.assertEqual(band(100.1),"100-150");self.assertEqual(band(150),">150")

    def test_square_surface_distance(self):
        # Camera offsets from a 50 m square center: inside, 10 m outside x, corner outside.
        def surface(dx,dy):return (max(abs(dx)-25,0)**2+max(abs(dy)-25,0)**2)**.5
        self.assertEqual(surface(20,20),0);self.assertEqual(surface(35,0),10);self.assertAlmostEqual(surface(35,35),14.1421356)


if __name__=="__main__":unittest.main()

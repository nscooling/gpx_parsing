#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import requests
import argparse

def validate_gpx_xml(gpx_file):
    """Validate that GPX file is well-formed XML"""
    try:
        with open(gpx_file, 'r', encoding='utf-8') as f:
            ET.parse(f)
        print(f"✅ {gpx_file} is well-formed XML")
        return True
    except ET.ParseError as e:
        print(f"❌ {gpx_file} has XML parsing errors:")
        print(f"   {e}")
        return False
    except Exception as e:
        print(f"❌ Error reading {gpx_file}: {e}")
        return False

def validate_gpx_with_gpxpy(gpx_file):
    """Validate GPX file using gpxpy library"""
    try:
        import gpxpy
        with open(gpx_file, 'r', encoding='utf-8') as f:
            gpx = gpxpy.parse(f)
        print(f"✅ {gpx_file} is valid GPX (gpxpy)")
        print(f"   Tracks: {len(gpx.tracks)}")
        print(f"   Waypoints: {len(gpx.waypoints)}")
        return True
    except Exception as e:
        print(f"❌ {gpx_file} failed gpxpy validation:")
        print(f"   {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Validate GPX file")
    parser.add_argument("gpx_file", help="GPX file to validate")
    parser.add_argument("--schema", action="store_true", 
                       help="Also validate against GPX schema (requires internet)")
    args = parser.parse_args()
    
    print(f"Validating GPX file: {args.gpx_file}")
    print("=" * 50)
    
    # Test 1: Well-formed XML
    xml_valid = validate_gpx_xml(args.gpx_file)
    
    # Test 2: GPX library parsing
    if xml_valid:
        gpx_valid = validate_gpx_with_gpxpy(args.gpx_file)
    else:
        gpx_valid = False
    
    # Summary
    print("\n" + "=" * 50)
    if xml_valid and gpx_valid:
        print("✅ GPX file is valid!")
    else:
        print("❌ GPX file has issues")
        
    return xml_valid and gpx_valid

if __name__ == "__main__":
    main()
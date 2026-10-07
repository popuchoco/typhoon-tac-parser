"""Convert the Natural Earth polygon shapefile to a small local GeoJSON crop."""

from __future__ import annotations

import json
import struct
from pathlib import Path


def read_polygon_records(path: Path):
    data = path.read_bytes()
    offset = 100
    while offset + 8 <= len(data):
        _, content_words = struct.unpack(">ii", data[offset : offset + 8])
        offset += 8
        content_size = content_words * 2
        content = data[offset : offset + content_size]
        offset += content_size
        if len(content) < 44:
            continue
        shape_type = struct.unpack("<i", content[:4])[0]
        if shape_type not in {5, 15, 25}:
            continue
        num_parts, num_points = struct.unpack("<ii", content[36:44])
        parts_offset = 44
        points_offset = parts_offset + num_parts * 4
        starts = struct.unpack(f"<{num_parts}i", content[parts_offset:points_offset])
        all_points = [
            struct.unpack("<dd", content[points_offset + index * 16 : points_offset + (index + 1) * 16])
            for index in range(num_points)
        ]
        rings = []
        for part_index, start in enumerate(starts):
            end = starts[part_index + 1] if part_index + 1 < len(starts) else num_points
            ring = [[round(lon, 5), round(lat, 5)] for lon, lat in all_points[start:end]]
            if len(ring) >= 4:
                rings.append(ring)
        if rings:
            yield rings


def intersects_view(rings, min_lon=95, max_lon=160, min_lat=5, max_lat=45):
    points = [point for ring in rings for point in ring]
    return any(min_lon <= lon <= max_lon and min_lat <= lat <= max_lat for lon, lat in points)


def main() -> None:
    source = Path("data/ne_50m_land_extract/ne_50m_land.shp")
    destination = Path("dashboard/assets/east-asia-land.geojson")
    destination.parent.mkdir(parents=True, exist_ok=True)
    features = []
    for rings in read_polygon_records(source):
        if not intersects_view(rings):
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "MultiPolygon", "coordinates": [[[point for point in ring]] for ring in rings]},
            }
        )
    destination.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    payload = {"type": "FeatureCollection", "features": features}
    (destination.parent / "east-asia-land.js").write_text(
        "window.TYPHOON_LAND_GEOJSON = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {destination} with {len(features)} features")


if __name__ == "__main__":
    main()

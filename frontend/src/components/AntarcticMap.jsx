import { Fragment } from "react";
import L from "leaflet";
import {
  CircleMarker,
  MapContainer,
  Marker,
  Popup,
  Rectangle,
  Tooltip,
} from "react-leaflet";

const vesselIcon = L.divIcon({
  className: "map-marker-shell",
  html: '<span class="map-marker vessel-marker" aria-label="Vessel">▲</span>',
  iconSize: [34, 34],
  iconAnchor: [17, 17],
});

const destinationIcon = L.divIcon({
  className: "map-marker-shell",
  html: '<span class="map-marker destination-marker" aria-label="Destination">●</span>',
  iconSize: [34, 34],
  iconAnchor: [17, 17],
});

function icebergIcon(id) {
  return L.divIcon({
    className: "map-marker-shell",
    html: `<span class="map-marker iceberg-marker">◆</span><span class="iceberg-id">${id}</span>`,
    iconSize: [48, 38],
    iconAnchor: [24, 18],
  });
}

function concentrationStyle(cell) {
  if (cell.is_land) {
    return { fillColor: "#4d5865", fillOpacity: 0.95, color: "#768390" };
  }

  const concentration = cell.ice_concentration;
  if (concentration < 0.2) return { fillColor: "#0d3348", fillOpacity: 0.55 };
  if (concentration < 0.4) return { fillColor: "#286681", fillOpacity: 0.67 };
  if (concentration < 0.6) return { fillColor: "#69a8ba", fillOpacity: 0.74 };
  if (concentration < 0.8) return { fillColor: "#b9dbe0", fillOpacity: 0.82 };
  return { fillColor: "#edf8f7", fillOpacity: 0.92 };
}

function concentrationLabel(concentration) {
  if (concentration < 0.2) return "Low";
  if (concentration < 0.4) return "Moderate";
  if (concentration < 0.6) return "High";
  if (concentration < 0.8) return "Very high";
  return "Extreme";
}

export default function AntarcticMap({
  vessel,
  destination,
  icebergs,
  cells,
  route: _route,
  bounds,
}) {
  const midpointLat = (bounds.lat_min + bounds.lat_max) / 2;
  const longitudeScale = Math.cos((midpointLat * Math.PI) / 180);
  const maxRow = Math.max(...cells.map((cell) => cell.row));
  const maxCol = Math.max(...cells.map((cell) => cell.col));
  const cellHeightDeg = (bounds.lat_max - bounds.lat_min) / (maxRow + 1);
  const cellWidthDeg = (bounds.lon_max - bounds.lon_min) / (maxCol + 1);

  const projectPoint = (lat, lon) => [
    lat,
    bounds.lon_min + (lon - bounds.lon_min) * longitudeScale,
  ];
  const projectedBounds = [
    projectPoint(bounds.lat_min, bounds.lon_min),
    projectPoint(bounds.lat_max, bounds.lon_max),
  ];

  return (
    <div className="map-layout">
      <MapContainer
        className="antarctic-map"
        crs={L.CRS.Simple}
        bounds={projectedBounds}
        maxBounds={projectedBounds}
        maxBoundsViscosity={1}
        minZoom={4}
        zoomSnap={0.25}
        attributionControl={false}
      >
        <Rectangle
          bounds={projectedBounds}
          pathOptions={{ color: "#3c9fc4", weight: 2, fillColor: "#061825", fillOpacity: 1 }}
        />

        {cells.map((cell) => {
          const halfHeight = cellHeightDeg / 2;
          const halfWidth = cellWidthDeg / 2;
          const cellBounds = [
            projectPoint(cell.lat - halfHeight, cell.lon - halfWidth),
            projectPoint(cell.lat + halfHeight, cell.lon + halfWidth),
          ];
          const style = concentrationStyle(cell);
          return (
            <Rectangle
              key={`${cell.row}-${cell.col}`}
              bounds={cellBounds}
              pathOptions={{ ...style, color: style.color || "#2c6173", weight: 0.35 }}
            >
              <Tooltip sticky>
                <div className="cell-tooltip">
                  <strong>Cell {cell.row}, {cell.col}</strong>
                  {cell.is_land ? (
                    <span>Land / non-navigable</span>
                  ) : (
                    <>
                      <span>{concentrationLabel(cell.ice_concentration)} sea ice · {(cell.ice_concentration * 100).toFixed(1)}%</span>
                      <span>Wind {cell.wind_speed_ms.toFixed(1)} m/s → {cell.wind_direction_deg.toFixed(0)}°</span>
                      <span>Current {cell.current_speed_ms.toFixed(2)} m/s → {cell.current_direction_deg.toFixed(0)}°</span>
                    </>
                  )}
                </div>
              </Tooltip>
            </Rectangle>
          );
        })}

        {icebergs.map((iceberg) => {
          const position = projectPoint(iceberg.lat, iceberg.lon);
          return (
            <Fragment key={iceberg.id}>
              <CircleMarker
                center={position}
                radius={7 + iceberg.safety_buffer_km}
                pathOptions={{
                  color: "#75d9ee",
                  weight: 1,
                  dashArray: "4 4",
                  fillColor: "#75d9ee",
                  fillOpacity: 0.08,
                }}
              />
              <Marker position={position} icon={icebergIcon(iceberg.id)}>
                <Popup>
                  <strong>{iceberg.id}</strong><br />
                  Radius: {iceberg.radius_km} km<br />
                  Safety buffer: {iceberg.safety_buffer_km} km<br />
                  Motion: {iceberg.velocity_kmh} km/h toward {iceberg.heading_deg}°
                </Popup>
              </Marker>
            </Fragment>
          );
        })}

        <Marker position={projectPoint(vessel.lat, vessel.lon)} icon={vesselIcon} zIndexOffset={1000}>
          <Popup>
            <strong>{vessel.name}</strong><br />
            {vessel.id}<br />
            Open-water speed: {vessel.speed_knots_open_water} knots
          </Popup>
        </Marker>

        <Marker
          position={projectPoint(destination.lat, destination.lon)}
          icon={destinationIcon}
          zIndexOffset={900}
        >
          <Popup><strong>{destination.name}</strong></Popup>
        </Marker>
      </MapContainer>

      <div className="map-overlay map-title">
        <span>BOUNDED CORRIDOR</span>
        <strong>69.5°S–66.5°S · 71°E–79°E</strong>
      </div>

      <div className="map-overlay legend" aria-label="Sea ice concentration legend">
        <strong>Sea-ice concentration</strong>
        <div className="legend-scale">
          <span className="swatch low" />
          <span className="swatch moderate" />
          <span className="swatch high" />
          <span className="swatch very-high" />
          <span className="swatch extreme" />
        </div>
        <div className="legend-labels"><span>0</span><span>0.5</span><span>1.0</span></div>
        <div className="legend-land"><span className="land-swatch" /> Land / non-navigable</div>
      </div>

    </div>
  );
}

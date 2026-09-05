import { Fragment, useMemo } from "react";
import L from "leaflet";
import {
  CircleMarker,
  MapContainer,
  Marker,
  Pane,
  Polyline,
  Popup,
  Rectangle,
  Tooltip,
} from "react-leaflet";

const vesselSprite = `
  <svg class="pixel-sprite" viewBox="0 0 32 32" aria-label="Vessel" shape-rendering="crispEdges">
    <rect x="14" y="2" width="4" height="4" fill="#f6f4cf"/>
    <rect x="11" y="6" width="10" height="4" fill="#f6f4cf"/>
    <rect x="8" y="10" width="16" height="5" fill="#ffcf4a"/>
    <rect x="5" y="15" width="22" height="5" fill="#ffcf4a"/>
    <rect x="8" y="20" width="16" height="4" fill="#e4553f"/>
    <rect x="11" y="24" width="10" height="4" fill="#e4553f"/>
    <rect x="14" y="28" width="4" height="3" fill="#f6f4cf"/>
    <rect x="13" y="9" width="2" height="4" fill="#081a3a"/>
    <rect x="17" y="9" width="2" height="4" fill="#081a3a"/>
  </svg>`;

const destinationSprite = `
  <svg class="pixel-sprite" viewBox="0 0 32 32" aria-label="Destination" shape-rendering="crispEdges">
    <rect x="13" y="0" width="6" height="8" fill="#6dff88"/>
    <rect x="13" y="24" width="6" height="8" fill="#6dff88"/>
    <rect x="0" y="13" width="8" height="6" fill="#6dff88"/>
    <rect x="24" y="13" width="8" height="6" fill="#6dff88"/>
    <rect x="9" y="9" width="14" height="14" fill="#1e5a76"/>
    <rect x="12" y="12" width="8" height="8" fill="#f6f4cf"/>
    <rect x="15" y="15" width="3" height="3" fill="#e4553f"/>
  </svg>`;

const icebergSprite = `
  <svg class="pixel-sprite iceberg-sprite" viewBox="0 0 38 32" aria-label="Iceberg" shape-rendering="crispEdges">
    <rect x="15" y="2" width="8" height="4" fill="#ffffff"/>
    <rect x="10" y="6" width="18" height="5" fill="#ffffff"/>
    <rect x="6" y="11" width="27" height="6" fill="#e9ffff"/>
    <rect x="2" y="17" width="34" height="7" fill="#c9f3ff"/>
    <rect x="7" y="24" width="25" height="5" fill="#8fd4e7"/>
    <rect x="11" y="11" width="4" height="4" fill="#b8e9f5"/>
    <rect x="25" y="17" width="5" height="4" fill="#92d5e7"/>
  </svg>`;

const vesselIcon = L.divIcon({
  className: "map-marker-shell vessel-icon",
  html: vesselSprite,
  iconSize: [42, 42],
  iconAnchor: [21, 21],
});

const destinationIcon = L.divIcon({
  className: "map-marker-shell destination-icon",
  html: destinationSprite,
  iconSize: [38, 38],
  iconAnchor: [19, 19],
});

const icebergIcons = {
  small: L.divIcon({ className: "map-marker-shell", html: icebergSprite, iconSize: [24, 20], iconAnchor: [12, 11] }),
  medium: L.divIcon({ className: "map-marker-shell", html: icebergSprite, iconSize: [28, 24], iconAnchor: [14, 13] }),
  large: L.divIcon({ className: "map-marker-shell", html: icebergSprite, iconSize: [32, 27], iconAnchor: [16, 15] }),
};

function icebergIconFor(radiusKm) {
  if (radiusKm >= 1.75) return icebergIcons.large;
  if (radiusKm >= 1.2) return icebergIcons.medium;
  return icebergIcons.small;
}

function concentrationStyle(cell) {
  if (cell.is_land) {
    return {
      fillColor: "#28263b",
      fillOpacity: 1,
      color: "#f05474",
      weight: 1.15,
      className: "blocked-cell",
    };
  }

  const concentration = cell.ice_concentration;
  if (concentration < 0.2) return { fillColor: "#172f8a", fillOpacity: 0.9 };
  if (concentration < 0.4) return { fillColor: "#2364aa", fillOpacity: 0.92 };
  if (concentration < 0.6) return { fillColor: "#54a8d4", fillOpacity: 0.94 };
  if (concentration < 0.8) return { fillColor: "#a7e3ed", fillOpacity: 0.96 };
  return { fillColor: "#f6f4cf", fillOpacity: 1 };
}

function riskStyle(riskCell) {
  if (!riskCell) {
    return { fillColor: "#302d49", fillOpacity: 1, color: "#f05474", weight: 1.15 };
  }
  if (!riskCell.is_navigable) {
    const blockedStyles = {
      land: { fillColor: "#242233", color: "#ff4f70" },
      heavy_ice: { fillColor: "#71354f", color: "#ff8ba2" },
      iceberg_exclusion: { fillColor: "#7b4521", color: "#ffcf4a" },
    };
    const blockedStyle = blockedStyles[riskCell.block_reason] || blockedStyles.land;
    return {
      ...blockedStyle,
      fillOpacity: 1,
      weight: 1.3,
      className: "blocked-cell",
    };
  }

  const risk = riskCell.total_risk;
  if (risk < 20) return { fillColor: "#2db85c", fillOpacity: 0.93 };
  if (risk < 40) return { fillColor: "#a8c744", fillOpacity: 0.94 };
  if (risk < 60) return { fillColor: "#f0c24b", fillOpacity: 0.95 };
  if (risk < 80) return { fillColor: "#ed863e", fillOpacity: 0.97 };
  return { fillColor: "#e33d4f", fillOpacity: 1 };
}

function concentrationLabel(concentration) {
  if (concentration < 0.2) return "LOW";
  if (concentration < 0.4) return "MODERATE";
  if (concentration < 0.6) return "HIGH";
  if (concentration < 0.8) return "VERY HIGH";
  return "EXTREME";
}

function CellReadout({ cell, riskCell }) {
  return (
    <div className="cell-readout">
      <div className="readout-title">CELL {String(cell.row).padStart(2, "0")}:{String(cell.col).padStart(2, "0")}</div>
      <dl>
        <dt>POSITION</dt>
        <dd>{Math.abs(cell.lat).toFixed(3)}°S / {cell.lon.toFixed(3)}°E</dd>
        <dt>SEA ICE</dt>
        <dd>{(cell.ice_concentration * 100).toFixed(1)}% · {concentrationLabel(cell.ice_concentration)}</dd>
        <dt>WIND</dt>
        <dd>{cell.wind_speed_ms.toFixed(1)} m/s → {cell.wind_direction_deg.toFixed(0)}°</dd>
        <dt>CURRENT</dt>
        <dd>{cell.current_speed_ms.toFixed(2)} m/s → {cell.current_direction_deg.toFixed(0)}°</dd>
        <dt>NAVIGATION</dt>
        <dd className={riskCell?.is_navigable ? "readout-safe" : "readout-blocked"}>
          {riskCell?.is_navigable ? "PASSABLE" : `BLOCKED · ${riskCell?.block_reason || "NO DATA"}`}
        </dd>
        <dt>TOTAL RISK</dt>
        <dd>{riskCell ? riskCell.total_risk.toFixed(1) : "—"} / 100</dd>
      </dl>
      {riskCell && (
        <div className="risk-breakdown">
          {Object.entries(riskCell.components).map(([name, component]) => (
            <div key={name}>
              <span>{name.replace("_", " ").toUpperCase()}</span>
              <span>{component.raw.toFixed(1)} RAW</span>
              <strong>+{component.weighted.toFixed(1)}</strong>
            </div>
          ))}
          <small>NEAREST ICEBERG: {riskCell.components.iceberg.nearest_iceberg_id || "NONE"}</small>
        </div>
      )}
    </div>
  );
}

export default function AntarcticMap({
  vessel,
  destination,
  icebergs,
  originIcebergs = [],
  cells,
  riskCells,
  layerMode,
  route,
  routeRaw,
  routes = [],
  showAlternate = false,
  bounds,
  forecastHour = 0,
  committedRoute = null,
  hazard = null,
}) {
  const midpointLat = (bounds.lat_min + bounds.lat_max) / 2;
  const longitudeScale = Math.cos((midpointLat * Math.PI) / 180);
  const maxRow = Math.max(...cells.map((cell) => cell.row));
  const maxCol = Math.max(...cells.map((cell) => cell.col));
  const cellHeightDeg = (bounds.lat_max - bounds.lat_min) / (maxRow + 1);
  const cellWidthDeg = (bounds.lon_max - bounds.lon_min) / (maxCol + 1);
  const riskByCell = useMemo(
    () => new Map(riskCells.map((cell) => [`${cell.row}-${cell.col}`, cell])),
    [riskCells],
  );
  const originById = useMemo(
    () => new Map(originIcebergs.map((iceberg) => [iceberg.id, iceberg])),
    [originIcebergs],
  );

  const projectPoint = (lat, lon) => [
    lat,
    bounds.lon_min + (lon - bounds.lon_min) * longitudeScale,
  ];
  const projectedBounds = [
    projectPoint(bounds.lat_min, bounds.lon_min),
    projectPoint(bounds.lat_max, bounds.lon_max),
  ];
  const displayRoutes = routes.length
    ? routes
    : route?.length
      ? [{ mode: "balanced", points: route, color: "#6dff88", active: true }]
      : [];

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
        preferCanvas
      >
        <Rectangle
          bounds={projectedBounds}
          pathOptions={{ color: "#69e6ff", weight: 3, fillColor: "#07194f", fillOpacity: 1 }}
        />

        {cells.map((cell) => {
          const cellKey = `${cell.row}-${cell.col}`;
          const riskCell = riskByCell.get(cellKey);
          const halfHeight = cellHeightDeg / 2;
          const halfWidth = cellWidthDeg / 2;
          const cellBounds = [
            projectPoint(cell.lat - halfHeight, cell.lon - halfWidth),
            projectPoint(cell.lat + halfHeight, cell.lon + halfWidth),
          ];
          const style = layerMode === "risk" ? riskStyle(riskCell) : concentrationStyle(cell);
          return (
            <Rectangle
              key={cellKey}
              bounds={cellBounds}
              pathOptions={{ ...style, color: style.color || "#5572c4", weight: style.weight || 0.45 }}
            >
              <Tooltip sticky className="pixel-tooltip">
                <strong>GRID {String(cell.row).padStart(2, "0")}:{String(cell.col).padStart(2, "0")}</strong>
                <span>
                  {layerMode === "risk" && riskCell
                    ? riskCell.is_navigable
                      ? `RISK ${riskCell.total_risk.toFixed(1)}`
                      : `BLOCKED / ${riskCell.block_reason.toUpperCase()}`
                    : `ICE ${(cell.ice_concentration * 100).toFixed(1)}%`}
                </span>
              </Tooltip>
              <Popup className="pixel-popup" minWidth={270}>
                <CellReadout cell={cell} riskCell={riskCell} />
              </Popup>
            </Rectangle>
          );
        })}

        <Pane name="route-lines" style={{ zIndex: 550 }}>
          {hazard?.alert && committedRoute?.length > 1 && <Polyline positions={committedRoute.map((point) => projectPoint(point.lat, point.lon))} pathOptions={{ color: "#ff4f70", weight: 6, dashArray: "8 8", opacity: 0.95 }} />}
          {showAlternate && hazard?.alternate_route?.route?.length > 1 && <Polyline positions={hazard.alternate_route.route.map((point) => projectPoint(point.lat, point.lon))} pathOptions={{ color: "#6dff88", weight: 7, opacity: 1 }} />}
          {routeRaw?.length > 1 && (
            <Polyline
              positions={routeRaw.map((point) => projectPoint(point.lat, point.lon))}
              pathOptions={{
                color: "#f6f4cf",
                weight: 2,
                opacity: 0.75,
                dashArray: "4 6",
                className: "raw-route-line",
              }}
            />
          )}
          {displayRoutes.map((displayRoute) => (
            <Polyline
              key={displayRoute.mode}
              positions={displayRoute.points.map((point) => projectPoint(point.lat, point.lon))}
              pathOptions={{
                color: displayRoute.color,
                weight: displayRoute.active ? 6 : 3,
                opacity: displayRoute.active ? 1 : 0.72,
                className: `route-line route-${displayRoute.mode}`,
              }}
            >
              <Tooltip sticky className="pixel-tooltip">
                <strong>{displayRoute.mode.toUpperCase()} ROUTE</strong>
              </Tooltip>
            </Polyline>
          ))}
        </Pane>

        {icebergs.map((iceberg) => {
          const position = projectPoint(iceberg.lat, iceberg.lon);
          const origin = originById.get(iceberg.id);
          return (
            <Fragment key={iceberg.id}>
              {forecastHour > 0 && origin && <><CircleMarker center={projectPoint(origin.lat, origin.lon)} radius={5} pathOptions={{ color: "#aab8df", fillColor: "#fff", fillOpacity: 0.2, opacity: 0.5 }} /><Polyline positions={[projectPoint(origin.lat, origin.lon), position]} pathOptions={{ color: iceberg.id === "IB-04" ? "#ffcf4a" : "#aab8df", weight: iceberg.id === "IB-04" ? 3 : 1, dashArray: "3 5" }} /></>}
              <CircleMarker
                center={position}
                radius={Math.min(10, 5 + iceberg.safety_buffer_km * 0.9)}
                pathOptions={{
                  color: "#f6f4cf",
                  weight: 1.5,
                  dashArray: "3 4",
                  fillColor: "#caf7ff",
                  fillOpacity: 0.09,
                  className: "iceberg-buffer",
                }}
              />
              <Marker
                position={position}
                icon={icebergIconFor(iceberg.radius_km)}
                riseOnHover
              >
                <Tooltip direction="top" offset={[0, -12]} className="pixel-tooltip">
                  <strong>{iceberg.id}</strong>
                </Tooltip>
                <Popup className="pixel-popup">
                  <div className="marker-readout">
                    <strong>{iceberg.id} / ICE CONTACT</strong>
                    <span>RADIUS {iceberg.radius_km} km</span>
                    <span>BUFFER {iceberg.safety_buffer_km} km</span>
                    <span>DRIFT {iceberg.velocity_kmh} km/h → {iceberg.heading_deg}°</span>
                  </div>
                </Popup>
              </Marker>
            </Fragment>
          );
        })}

        <Marker position={projectPoint(vessel.lat, vessel.lon)} icon={vesselIcon} zIndexOffset={1000}>
          <Tooltip permanent direction="right" offset={[15, 0]} className="unit-label">RV-01</Tooltip>
          <Popup className="pixel-popup">
            <div className="marker-readout">
              <strong>{vessel.name}</strong>
              <span>CALLSIGN {vessel.id}</span>
              <span>OPEN WATER {vessel.speed_knots_open_water} kn</span>
            </div>
          </Popup>
        </Marker>

        <Marker position={projectPoint(destination.lat, destination.lon)} icon={destinationIcon} zIndexOffset={900}>
          <Tooltip permanent direction="left" offset={[-14, 0]} className="unit-label">DEST</Tooltip>
          <Popup className="pixel-popup"><strong>{destination.name}</strong></Popup>
        </Marker>
      </MapContainer>

      <div className="map-overlay map-title">
        <span>SECTOR PRYDZ-01 // {forecastHour ? `FORECAST +${forecastHour}H` : "CURRENT CONDITIONS"} // {layerMode === "risk" ? "NAVIGATION RISK" : "SEA-ICE SCAN"}</span>
        <strong>69.5°S–66.5°S / 71°E–79°E</strong>
      </div>
      <div className="map-overlay map-instruction">CLICK CELL FOR ANALYSIS</div>
      {displayRoutes.length > 1 && (
        <div className="map-overlay route-map-legend">
          {displayRoutes.map((displayRoute) => (
            <span key={displayRoute.mode}>
              <i style={{ backgroundColor: displayRoute.color }} />
              {displayRoute.mode.toUpperCase()}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

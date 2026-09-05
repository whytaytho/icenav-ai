import { Fragment } from "react";
import L from "leaflet";
import { CircleMarker, MapContainer, Polyline, Rectangle, Tooltip } from "react-leaflet";

const MODEL_COLORS = { persistence: "#ffcf4a", ml: "#69e6ff", free_drift: "#ff5fcf" };

export default function ValidationTrackMap({ results }) {
  const available = Object.entries(results).filter(([, result]) => result?.available !== false && result?.predictions?.length);
  if (!available.length) return <div className="validation-map-empty">SELECT A CASE WITH AN OBSERVED +24H POSITION</div>;

  const reference = available[0][1];
  const points = [reference.origin];
  available.forEach(([, result]) => result.predictions.forEach((prediction) => points.push(prediction.predicted, prediction.observed)));
  const latitudes = points.map((point) => point.lat);
  const longitudes = points.map((point) => point.lon);
  const latPadding = Math.max(0.08, (Math.max(...latitudes) - Math.min(...latitudes)) * 0.35);
  const lonPadding = Math.max(0.12, (Math.max(...longitudes) - Math.min(...longitudes)) * 0.35);
  const bounds = [
    [Math.min(...latitudes) - latPadding, Math.min(...longitudes) - lonPadding],
    [Math.max(...latitudes) + latPadding, Math.max(...longitudes) + lonPadding],
  ];
  const observedPoints = [reference.origin, ...reference.predictions.map((prediction) => prediction.observed)];

  return (
    <div className="validation-map-shell">
      <MapContainer key={JSON.stringify(bounds)} className="validation-track-map" crs={L.CRS.Simple} bounds={bounds} maxBounds={bounds} attributionControl={false} preferCanvas>
        <Rectangle bounds={bounds} pathOptions={{ color: "#5572c4", fillColor: "#07194f", fillOpacity: 1, weight: 2 }} />
        <Polyline positions={observedPoints.map((point) => [point.lat, point.lon])} pathOptions={{ color: "#6dff88", weight: 5 }}>
          <Tooltip sticky className="pixel-tooltip">OBSERVED TRACK</Tooltip>
        </Polyline>
        {available.map(([model, result]) => {
          const color = MODEL_COLORS[model] || "#f6f4cf";
          const predictedPoints = [result.origin, ...result.predictions.map((prediction) => prediction.predicted)];
          return (
            <Fragment key={model}>
              <Polyline positions={predictedPoints.map((point) => [point.lat, point.lon])} pathOptions={{ color, weight: 4, dashArray: "7 6" }} />
              {result.predictions.map((prediction) => (
                <Polyline key={`${model}-${prediction.horizon_hours}`} positions={[[prediction.predicted.lat, prediction.predicted.lon], [prediction.observed.lat, prediction.observed.lon]]} pathOptions={{ color: "#ff4f70", weight: 2, dashArray: "2 5" }} />
              ))}
              {result.predictions.map((prediction) => (
                <CircleMarker key={`${model}-point-${prediction.horizon_hours}`} center={[prediction.predicted.lat, prediction.predicted.lon]} radius={6} pathOptions={{ color, fillColor: color, fillOpacity: 1 }}>
                  <Tooltip direction="top" className="pixel-tooltip">{model.toUpperCase()} +{prediction.horizon_hours}H // {prediction.error_km.toFixed(2)} KM ERROR</Tooltip>
                </CircleMarker>
              ))}
            </Fragment>
          );
        })}
        <CircleMarker center={[reference.origin.lat, reference.origin.lon]} radius={7} pathOptions={{ color: "#f6f4cf", fillColor: "#f6f4cf", fillOpacity: 1 }}><Tooltip className="pixel-tooltip">T0 OBSERVATION</Tooltip></CircleMarker>
        {reference.predictions.map((prediction) => <CircleMarker key={`observed-${prediction.horizon_hours}`} center={[prediction.observed.lat, prediction.observed.lon]} radius={7} pathOptions={{ color: "#6dff88", fillColor: "#6dff88", fillOpacity: 1 }}><Tooltip className="pixel-tooltip">OBSERVED +{prediction.horizon_hours}H</Tooltip></CircleMarker>)}
      </MapContainer>
      <div className="validation-map-key"><span><i className="observed" />OBSERVED</span><span><i className="predicted" />PREDICTED</span><span><i className="error" />POSITION ERROR</span></div>
    </div>
  );
}

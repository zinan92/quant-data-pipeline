import { useQuery } from "@tanstack/react-query";
import { apiFetch, REFRESH_INTERVALS } from "../utils/api";

interface TrackInfo {
  name: string;
  concepts: string[];
  total_stocks: number;
}

interface TracksResponse {
  tracks: TrackInfo[];
}

interface Props {
  onTrackClick: (trackName: string) => void;
}

async function fetchTracks(): Promise<TracksResponse> {
  const response = await apiFetch("/api/tracks");
  if (!response.ok) {
    throw new Error("Failed to fetch tracks");
  }
  return response.json();
}

export function TracksView({ onTrackClick }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["tracks"],
    queryFn: fetchTracks,
    staleTime: REFRESH_INTERVALS.boards,
  });

  if (isLoading) {
    return <div className="tracks-view__loading">加载赛道...</div>;
  }

  if (error || !data) {
    return <div className="tracks-view__error">加载失败</div>;
  }

  return (
    <div className="tracks-view">
      <div className="tracks-view__header">
        <h2 className="tracks-view__title">我的赛道</h2>
        <p className="tracks-view__subtitle">关注的概念板块</p>
      </div>
      <div className="tracks-view__grid">
        {data.tracks.map((track) => (
          <div
            key={track.name}
            className="track-card"
            onClick={() => onTrackClick(track.name)}
          >
            <div className="track-card__header">
              <h3 className="track-card__name">{track.name}</h3>
              <span className="track-card__count">{track.total_stocks}只</span>
            </div>
            <div className="track-card__concepts">
              {track.concepts.map((concept) => (
                <span key={concept} className="track-card__concept-tag">
                  {concept}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

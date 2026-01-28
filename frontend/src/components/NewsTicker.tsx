/**
 * 新闻快讯滚动条组件
 */
import { useEffect, useState } from 'react';

interface NewsItem {
  source: string;
  source_name: string;
  title: string;
  content: string;
  time: string;
  url?: string;
}

interface Props {
  refreshInterval?: number; // 刷新间隔（毫秒）
}

async function fetchNews(): Promise<NewsItem[]> {
  try {
    const response = await fetch('/api/news/latest?limit=20');
    if (!response.ok) return [];
    const data = await response.json();
    return data.news || [];
  } catch {
    return [];
  }
}

export function NewsTicker({ refreshInterval = 30000 }: Props) {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const data = await fetchNews();
      setNews(data);
      setLoading(false);
    };

    load();
    const interval = setInterval(load, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval]);

  if (loading) {
    return <div className="news-ticker news-ticker--loading">加载快讯中...</div>;
  }

  if (news.length === 0) {
    return null;
  }

  return (
    <div className="news-ticker">
      <span className="news-ticker__label">📰 快讯</span>
      <div className="news-ticker__content">
        <div className="news-ticker__scroll">
          {news.map((item, index) => (
            <span key={index} className="news-ticker__item">
              <span className="news-ticker__source">[{item.source_name}]</span>
              <span className="news-ticker__title">{item.title}</span>
              <span className="news-ticker__separator">|</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

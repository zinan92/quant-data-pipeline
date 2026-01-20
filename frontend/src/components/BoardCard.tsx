interface BoardData {
  排名: number;
  板块名称: string;
  板块代码: string;
  最新价: number;
  涨跌额: number;
  涨跌幅: number;
  总市值: number;
  换手率: number;
  上涨家数: number;
  下跌家数: number;
  领涨股票: string;
  "领涨股票-涨跌幅": number;
  行业PE?: number | null;
}

interface Props {
  board: BoardData;
  rank: number;
  onClick: () => void;
}

export function BoardCard({ board, rank, onClick }: Props) {
  const isPositive = board.涨跌幅 >= 0;
  const changeClass = isPositive ? "board-card__change--positive" : "board-card__change--negative";

  return (
    <article className="board-card" onClick={onClick}>
      <div className="board-card__rank">#{rank}</div>
      <header className="board-card__header">
        <h3 className="board-card__title">{board.板块名称}</h3>
        <div className={`board-card__change ${changeClass}`}>
          {isPositive ? "+" : ""}{board.涨跌幅.toFixed(2)}%
        </div>
      </header>
      <footer className="board-card__stats">
        <span className="board-card__stat board-card__stat--up">
          ↑ {board.上涨家数}
        </span>
        <span className="board-card__stat board-card__stat--down">
          ↓ {board.下跌家数}
        </span>
        {board.行业PE && (
          <span className="board-card__stat board-card__stat--pe">
            PE {board.行业PE}
          </span>
        )}
      </footer>
    </article>
  );
}

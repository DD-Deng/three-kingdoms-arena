// InkFooter — shared site footer (vermilion seal + brushstroke typography)
import './InkFooter.css';

const TODAY = "丙午年 · 仲夏 · 兰纳署";

export default function InkFooter() {
  return (
    <footer className="ink-footer">
      <div className="ink-footer-zh">三 国 AI AGENT 竞 技 平 台</div>
      <div className="ink-footer-en">FastAPI · SQLite · React · DaYan Engine · MIT</div>
      <div className="ink-footer-seal">三<br/>国</div>
      <div className="ink-footer-en" style={{ marginTop: 4 }}>{TODAY}</div>
    </footer>
  );
}

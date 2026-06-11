import type { RootCauseNode } from '../types';
import { pct } from '../utils/format';

function Node({ node }: { node: RootCauseNode }) {
  return (
    <div className="rc-node">
      <div className={`rc-card ${node.is_root_cause ? 'root' : ''}`}>
        <div className="rc-head">
          <span className="rc-name">{node.entity_name}</span>
          <span className="rc-type">{node.entity_type}</span>
          {node.is_root_cause && <span className="root-flag">ROOT CAUSE</span>}
        </div>
        {node.contribution && <div className="rc-contrib">{node.contribution}</div>}
        <div className="confidence-bar" aria-label={`confidence ${pct(node.confidence)}`}>
          <span style={{ width: pct(node.confidence) }} />
        </div>
        <div className="rc-type" style={{ marginTop: 4 }}>
          confidence {pct(node.confidence)}
        </div>
      </div>
      {node.children.map((c) => (
        <Node key={c.entity_id} node={c} />
      ))}
    </div>
  );
}

export function RootCauseTree({ root }: { root: RootCauseNode | null }) {
  if (!root) {
    return <div className="empty">No causal tree available for this problem.</div>;
  }
  return <Node node={root} />;
}

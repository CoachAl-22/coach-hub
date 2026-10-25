import { useState, useMemo } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, Dot } from "recharts";

const ATHLETES = {
  archer: {
    name: "Archer McHugh", initials: "AM", event: "100m / 200m", color: "#F26522",
    squad: "Performance",
    data: [
      { block: "Blk 13", label: "May '25", "20m": 3.02, "60m": 7.38, "150m": 18.2, slj: 2.48, vj: 42 },
      { block: "Blk 2",  label: "Jul '25", "20m": 2.95, "60m": 7.21, "150m": 17.8, slj: 2.55, vj: 44 },
      { block: "Blk 4",  label: "Sep '25", "20m": 2.91, "60m": 7.15, "150m": 17.5, slj: 2.58, vj: 46 },
      { block: "Blk 6",  label: "Nov '25", "20m": 2.87, "60m": 7.08, "150m": 17.1, slj: 2.63, vj: 47 },
      { block: "Blk 9",  label: "Feb '26", "20m": 2.85, "60m": 7.02, "150m": 16.9, slj: 2.67, vj: 49 },
    ]
  },
  luke: {
    name: "Luke Rollo", initials: "LR", event: "400m", color: "#00B4D8",
    squad: "Development",
    data: [
      { block: "Blk 13", label: "May '25", "20m": 3.15, "60m": 7.82, "150m": 20.1, slj: 2.35, vj: 38 },
      { block: "Blk 2",  label: "Jul '25", "20m": 3.05, "60m": 7.65, "150m": 19.5, slj: 2.42, vj: 40 },
      { block: "Blk 4",  label: "Sep '25", "20m": 2.98, "60m": 7.48, "150m": 19.0, slj: 2.48, vj: 42 },
      { block: "Blk 6",  label: "Nov '25", "20m": 2.93, "60m": 7.35, "150m": 18.6, slj: 2.52, vj: 43 },
      { block: "Blk 9",  label: "Feb '26", "20m": 2.90, "60m": 7.28, "150m": 18.2, slj: 2.55, vj: 44 },
    ]
  },
  dev: {
    name: "Dev Chico", initials: "DC", event: "200m / 400m", color: "#a78bfa",
    squad: "Development",
    data: [
      { block: "Blk 13", label: "May '25", "20m": 3.08, "60m": 7.55, "150m": 19.0, slj: 2.42, vj: 40 },
      { block: "Blk 2",  label: "Jul '25", "20m": 3.00, "60m": 7.40, "150m": 18.5, slj: 2.49, vj: 42 },
      { block: "Blk 4",  label: "Sep '25", "20m": 2.95, "60m": 7.28, "150m": 18.0, slj: 2.55, vj: 44 },
      { block: "Blk 6",  label: "Nov '25", "20m": 2.92, "60m": 7.18, "150m": 17.6, slj: 2.60, vj: 46 },
      { block: "Blk 9",  label: "Feb '26", "20m": 2.89, "60m": 7.10, "150m": 17.3, slj: 2.63, vj: 47 },
    ]
  }
};

const METRICS = {
  "20m":  { label: "20m Sprint",           unit: "s",  higherIsBetter: false, dec: 2, description: "Acceleration — first 20m from standing start" },
  "60m":  { label: "60m Sprint",           unit: "s",  higherIsBetter: false, dec: 2, description: "Speed development — full acceleration + max velocity" },
  "150m": { label: "150m Sprint",          unit: "s",  higherIsBetter: false, dec: 1, description: "Speed endurance — ability to sustain max velocity" },
  slj:    { label: "Standing Long Jump",   unit: "m",  higherIsBetter: true,  dec: 2, description: "Explosive leg power — horizontal force production" },
  vj:     { label: "Vertical Jump",        unit: "cm", higherIsBetter: true,  dec: 0, description: "Reactive leg power — vertical force production" },
};

const BENCHMARKS = {
  "20m":  { good: 2.90, state: 2.82, national: 2.75 },
  "60m":  { good: 7.10, state: 6.95, national: 6.75 },
  "150m": { good: 17.0, state: 16.5, national: 15.8 },
  slj:    { good: 2.55, state: 2.70, national: 2.85 },
  vj:     { good: 45,   state: 52,   national: 58 },
};

const BG = "#0a0a0a";
const CARD = "#161616";
const BORDER = "#2a2a2a";
const MUTED = "#888";
const TEXT = "#e0e0e0";

function PBDot(props) {
  const { cx, cy, payload, dataKey, isPB } = props;
  if (!isPB) return <circle cx={cx} cy={cy} r={4} fill={props.stroke} stroke={BG} strokeWidth={1.5}/>;
  return (
    <g>
      <circle cx={cx} cy={cy} r={7} fill={props.stroke} stroke={BG} strokeWidth={2}/>
      <text x={cx} y={cy+1} textAnchor="middle" dominantBaseline="central" fill="#fff" fontSize={8} fontWeight="bold">★</text>
    </g>
  );
}

function CustomTooltip({ active, payload, label, metric, athleteColor }) {
  if (!active || !payload?.length) return null;
  const m = METRICS[metric];
  const bm = BENCHMARKS[metric];
  const val = payload[0]?.value;
  if (!val) return null;
  const vs = m.higherIsBetter ? val >= bm.national : val <= bm.national;
  const vsState = m.higherIsBetter ? val >= bm.state : val <= bm.state;
  const vsGood = m.higherIsBetter ? val >= bm.good : val <= bm.good;
  const level = vs ? "National" : vsState ? "State" : vsGood ? "Good" : "Building";
  const levelColor = vs ? "#34d399" : vsState ? "#00B4D8" : vsGood ? "#F26522" : MUTED;
  return (
    <div style={{background:CARD,border:`0.5px solid ${BORDER}`,borderRadius:8,padding:"10px 14px",fontSize:12}}>
      <div style={{color:MUTED,marginBottom:4}}>{label}</div>
      <div style={{color:athleteColor,fontSize:16,fontWeight:500}}>{val.toFixed(m.dec)} {m.unit}</div>
      <div style={{color:levelColor,marginTop:4,fontSize:11}}>{level} standard</div>
      <div style={{marginTop:6,borderTop:`0.5px solid ${BORDER}`,paddingTop:6,display:"flex",flexDirection:"column",gap:2}}>
        <div style={{color:MUTED,fontSize:10}}>Good: {bm.good} · State: {bm.state} · National: {bm.national}</div>
      </div>
    </div>
  );
}

export default function AthleteDashboard() {
  const [selectedAthlete, setSelectedAthlete] = useState("archer");
  const [selectedMetric, setSelectedMetric] = useState("20m");

  const athlete = ATHLETES[selectedAthlete];
  const metric = METRICS[selectedMetric];
  const bm = BENCHMARKS[selectedMetric];

  const data = athlete.data;
  const values = data.map(d => d[selectedMetric]);
  const first = values[0];
  const latest = values[values.length - 1];
  const pb = metric.higherIsBetter ? Math.max(...values) : Math.min(...values);
  const pbIdx = metric.higherIsBetter ? values.indexOf(pb) : values.indexOf(pb);
  const improvement = metric.higherIsBetter ? ((latest - first) / first * 100) : ((first - latest) / first * 100);
  const isImproved = improvement > 0;

  const chartData = data.map((d, i) => ({
    ...d,
    value: d[selectedMetric],
    isPB: i === pbIdx
  }));

  const yDomain = useMemo(() => {
    const padding = metric.higherIsBetter ? 0.15 : 0.05;
    const allVals = [...values, bm.good, bm.state, bm.national];
    const min = Math.min(...allVals);
    const max = Math.max(...allVals);
    const range = max - min;
    return metric.higherIsBetter
      ? [+(min - range * 0.08).toFixed(2), +(max + range * 0.08).toFixed(2)]
      : [+(min - range * 0.05).toFixed(2), +(max + range * 0.12).toFixed(2)];
  }, [selectedMetric, selectedAthlete]);

  const bmLevel = (val) => {
    if (metric.higherIsBetter) {
      if (val >= bm.national) return { label: "National", color: "#34d399" };
      if (val >= bm.state)    return { label: "State",    color: "#00B4D8" };
      if (val >= bm.good)     return { label: "Good",     color: "#F26522" };
      return { label: "Building", color: MUTED };
    } else {
      if (val <= bm.national) return { label: "National", color: "#34d399" };
      if (val <= bm.state)    return { label: "State",    color: "#00B4D8" };
      if (val <= bm.good)     return { label: "Good",     color: "#F26522" };
      return { label: "Building", color: MUTED };
    }
  };

  const latestLevel = bmLevel(latest);

  return (
    <div style={{fontFamily:"system-ui,sans-serif",background:BG,minHeight:600,padding:0}}>
      {/* Header */}
      <div style={{background:BG,padding:"14px 20px 12px",borderBottom:`0.5px solid ${BORDER}`,display:"flex",alignItems:"center",justifyContent:"space-between"}}>
        <div style={{display:"flex",alignItems:"baseline",gap:10}}>
          <span style={{fontSize:17,fontWeight:500,color:"#fff"}}>Performance</span>
          <span style={{fontSize:12,color:MUTED}}>2025/26 Season</span>
        </div>
        <span style={{fontSize:11,background:"rgba(242,101,34,.15)",color:"#F26522",padding:"2px 8px",borderRadius:20,fontWeight:500}}>
          {Object.keys(ATHLETES).length} athletes · {Object.keys(METRICS).length} metrics
        </span>
      </div>

      {/* Athlete selector */}
      <div style={{padding:"12px 20px 0",display:"flex",gap:8,overflowX:"auto"}}>
        {Object.entries(ATHLETES).map(([key, a]) => (
          <button key={key} onClick={() => setSelectedAthlete(key)}
            style={{display:"flex",alignItems:"center",gap:8,padding:"8px 14px",borderRadius:10,cursor:"pointer",
              background: selectedAthlete===key ? CARD : "transparent",
              border: selectedAthlete===key ? `1.5px solid ${a.color}` : `0.5px solid ${BORDER}`,
              whiteSpace:"nowrap", flexShrink:0}}>
            <div style={{width:28,height:28,borderRadius:"50%",background:`${a.color}22`,color:a.color,
              display:"flex",alignItems:"center",justifyContent:"center",fontSize:10,fontWeight:600}}>
              {a.initials}
            </div>
            <div style={{textAlign:"left"}}>
              <div style={{fontSize:13,fontWeight:500,color: selectedAthlete===key ? "#fff" : MUTED}}>{a.name}</div>
              <div style={{fontSize:10,color: selectedAthlete===key ? a.color : "#555"}}>{a.event}</div>
            </div>
          </button>
        ))}
      </div>

      {/* Metric selector */}
      <div style={{padding:"12px 20px",display:"flex",gap:6,flexWrap:"wrap"}}>
        {Object.entries(METRICS).map(([key, m]) => (
          <button key={key} onClick={() => setSelectedMetric(key)}
            style={{padding:"5px 12px",borderRadius:20,fontSize:12,cursor:"pointer",
              background: selectedMetric===key ? athlete.color : "transparent",
              border: selectedMetric===key ? `none` : `0.5px solid ${BORDER}`,
              color: selectedMetric===key ? "#fff" : MUTED,
              fontWeight: selectedMetric===key ? 500 : 400}}>
            {m.label}
          </button>
        ))}
      </div>

      {/* Stats row */}
      <div style={{padding:"0 20px 12px",display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:8}}>
        {[
          { label: "Latest", value: `${latest.toFixed(metric.dec)} ${metric.unit}`, sub: data[data.length-1].label, color: athlete.color },
          { label: "Personal best", value: `${pb.toFixed(metric.dec)} ${metric.unit}`, sub: data[pbIdx].label, color: "#34d399" },
          { label: "Improvement", value: `${isImproved ? "+" : ""}${improvement.toFixed(1)}%`, sub: "since first test", color: isImproved ? "#34d399" : "#f87171" },
          { label: "Standard", value: latestLevel.label, sub: `vs benchmarks`, color: latestLevel.color },
        ].map((s, i) => (
          <div key={i} style={{background:CARD,border:`0.5px solid ${BORDER}`,borderRadius:10,padding:"12px 14px"}}>
            <div style={{fontSize:10,color:MUTED,textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:4}}>{s.label}</div>
            <div style={{fontSize:18,fontWeight:500,color:s.color}}>{s.value}</div>
            <div style={{fontSize:10,color:"#555",marginTop:2}}>{s.sub}</div>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div style={{padding:"0 20px",marginBottom:12}}>
        <div style={{background:CARD,border:`0.5px solid ${BORDER}`,borderRadius:12,padding:"16px 12px 10px"}}>
          <div style={{display:"flex",alignItems:"baseline",gap:8,marginBottom:4,paddingLeft:4}}>
            <span style={{fontSize:13,fontWeight:500,color:"#fff"}}>{metric.label}</span>
            <span style={{fontSize:11,color:MUTED}}>{metric.description}</span>
          </div>
          <div style={{display:"flex",gap:12,paddingLeft:4,marginBottom:12}}>
            <span style={{fontSize:10,color:MUTED,display:"flex",alignItems:"center",gap:4}}>
              <span style={{display:"inline-block",width:20,height:1,borderTop:"1px dashed #888"}}></span>
              Good ({bm.good})
            </span>
            <span style={{fontSize:10,color:"#00B4D8",display:"flex",alignItems:"center",gap:4}}>
              <span style={{display:"inline-block",width:20,height:1,borderTop:"1px dashed #00B4D8"}}></span>
              State ({bm.state})
            </span>
            <span style={{fontSize:10,color:"#34d399",display:"flex",alignItems:"center",gap:4}}>
              <span style={{display:"inline-block",width:20,height:1,borderTop:"1px dashed #34d399"}}></span>
              National ({bm.national})
            </span>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chartData} margin={{top:10,right:16,bottom:0,left:-10}}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e1e1e" vertical={false}/>
              <XAxis dataKey="label" tick={{fill:MUTED,fontSize:11}} axisLine={{stroke:BORDER}} tickLine={false}/>
              <YAxis
                domain={yDomain}
                tick={{fill:MUTED,fontSize:11}}
                axisLine={false} tickLine={false}
                tickFormatter={v => v.toFixed(metric.dec)}
                reversed={!metric.higherIsBetter}
              />
              <Tooltip content={<CustomTooltip metric={selectedMetric} athleteColor={athlete.color}/>}/>
              <ReferenceLine y={bm.good}     stroke={MUTED}    strokeDasharray="4 3" strokeWidth={0.8}/>
              <ReferenceLine y={bm.state}    stroke="#00B4D8"  strokeDasharray="4 3" strokeWidth={0.8}/>
              <ReferenceLine y={bm.national} stroke="#34d399"  strokeDasharray="4 3" strokeWidth={0.8}/>
              <Line
                type="monotone" dataKey="value" stroke={athlete.color}
                strokeWidth={2} dot={(props) => {
                  const isPB = chartData[props.index]?.isPB;
                  return <PBDot {...props} isPB={isPB}/>;
                }}
                activeDot={{r:6, fill:athlete.color, stroke:BG, strokeWidth:2}}
              />
            </LineChart>
          </ResponsiveContainer>
          <div style={{textAlign:"center",fontSize:10,color:"#555",marginTop:4}}>
            ★ = Personal best · Testing points aligned to macrocycle blocks
          </div>
        </div>
      </div>

      {/* Results table */}
      <div style={{padding:"0 20px 20px"}}>
        <div style={{background:CARD,border:`0.5px solid ${BORDER}`,borderRadius:12,overflow:"hidden"}}>
          <div style={{padding:"12px 16px",borderBottom:`0.5px solid ${BORDER}`,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
            <span style={{fontSize:12,fontWeight:500,color:"#fff"}}>All results — {metric.label}</span>
            <span style={{fontSize:10,color:MUTED}}>Click to add new test result</span>
          </div>
          <table style={{width:"100%",borderCollapse:"collapse"}}>
            <thead>
              <tr style={{background:"#111"}}>
                {["Block","Date","Result","Benchmark","vs PB","Standard"].map(h => (
                  <td key={h} style={{padding:"8px 16px",fontSize:10,color:MUTED,textTransform:"uppercase",letterSpacing:"0.06em"}}>{h}</td>
                ))}
              </tr>
            </thead>
            <tbody>
              {chartData.map((row, i) => {
                const val = row.value;
                const isPB = row.isPB;
                const vs = metric.higherIsBetter ? val - pb : pb - val;
                const vsStr = vs === 0 ? "PB" : `${vs > 0 ? "+" : ""}${vs.toFixed(metric.dec)}`;
                const level = bmLevel(val);
                return (
                  <tr key={i} style={{borderBottom:`0.5px solid ${BORDER}`,background: isPB ? `${athlete.color}0a` : "transparent"}}>
                    <td style={{padding:"10px 16px",fontSize:12,color:MUTED}}>{row.block}</td>
                    <td style={{padding:"10px 16px",fontSize:12,color:TEXT}}>{row.label}</td>
                    <td style={{padding:"10px 16px",fontSize:13,fontWeight:500,color:isPB?athlete.color:TEXT}}>
                      {val.toFixed(metric.dec)} {metric.unit} {isPB ? "★" : ""}
                    </td>
                    <td style={{padding:"10px 16px"}}>
                      <span style={{fontSize:10,color:MUTED}}>Good: {bm.good}</span>
                    </td>
                    <td style={{padding:"10px 16px",fontSize:12,
                      color: vsStr==="PB" ? athlete.color : (vs < 0 ? "#f87171" : "#34d399")}}>
                      {vsStr}
                    </td>
                    <td style={{padding:"10px 16px"}}>
                      <span style={{fontSize:10,padding:"2px 8px",borderRadius:20,
                        background:`${level.color}22`,color:level.color,fontWeight:500}}>
                        {level.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

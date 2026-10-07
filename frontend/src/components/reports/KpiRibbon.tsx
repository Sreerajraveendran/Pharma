import { useState } from 'react';
import {
  TrendingDown,
  TrendingUp
} from 'lucide-react';
import { Sparkline } from './Visuals';

export default function KpiRibbon({ kpis }: { kpis: Record<string, any> }) {
  const [activeKpiGroup, setActiveKpiGroup] = useState('revenue'); // revenue, tax, collections
  const [expandedKpis, setExpandedKpis] = useState(false);

  return (
    <div className="bg-white border border-outline-variant rounded-xl p-4 space-y-3">
      <div className="flex justify-between items-center">
        <div className="flex bg-surface-container p-0.5 rounded-lg border border-outline-variant">
          <button
            onClick={() => setActiveKpiGroup('revenue')}
            className={`px-3 py-1 text-xs font-bold rounded-md transition-all ${activeKpiGroup === 'revenue' ? 'bg-white text-primary shadow-xs' : 'text-on-surface-variant'}`}
          >
            Revenue & Sales
          </button>
          <button
            onClick={() => setActiveKpiGroup('tax')}
            className={`px-3 py-1 text-xs font-bold rounded-md transition-all ${activeKpiGroup === 'tax' ? 'bg-white text-primary shadow-xs' : 'text-on-surface-variant'}`}
          >
            Taxes & Refunds
          </button>
          <button
            onClick={() => setActiveKpiGroup('collections')}
            className={`px-3 py-1 text-xs font-bold rounded-md transition-all ${activeKpiGroup === 'collections' ? 'bg-white text-primary shadow-xs' : 'text-on-surface-variant'}`}
          >
            Channels & Receivables
          </button>
        </div>

        <button
          onClick={() => setExpandedKpis(!expandedKpis)}
          className="text-xs font-bold text-primary hover:underline flex items-center gap-1"
        >
          {expandedKpis ? 'Collapse Ribbon' : 'Expand All 15 Metrics'}
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3.5">
        {/* Displaying dynamically according to filter tab or showing all if expanded */}
        {(() => {
          const getVisibleKpis = () => {
            if (expandedKpis) {
              return Object.keys(kpis);
            }
            if (activeKpiGroup === 'revenue') {
              return ["total_revenue", "net_revenue", "gross_sales", "avg_bill_value", "num_transactions"];
            }
            if (activeKpiGroup === 'tax') {
              return ["total_discounts", "gst_collected", "total_refunds", "prescriptions_billed"];
            }
            return ["cash_collection", "card_collection", "upi_collection", "insurance_receivables", "pending_payments"];
          };

          const visibleKeys = getVisibleKpis();
          return visibleKeys.map(key => {
            const card = kpis[key];
            if (!card) return null;
            const hasChange = card.change !== null && card.change !== undefined;
            const isNegative = hasChange && card.change < 0;

            return (
              <div key={key} className="bg-surface-container-low border border-outline-variant/60 rounded-xl p-3.5 flex flex-col justify-between hover:shadow-sm transition-all">
                <div className="flex justify-between items-start gap-2">
                  <span className="text-[10px] font-black uppercase text-outline tracking-wider line-clamp-1">{card.label}</span>
                  {hasChange ? (
                    <div className={`flex items-center gap-0.5 text-[10px] font-extrabold ${isNegative ? 'text-error' : 'text-secondary'}`}>
                      {isNegative ? <TrendingDown className="w-3 h-3" /> : <TrendingUp className="w-3 h-3" />}
                      <span>{isNegative ? '' : '+'}{card.change}%</span>
                    </div>
                  ) : (
                    <span className="text-[10px] font-bold text-outline" title="No data in the previous period to compare against">n/a</span>
                  )}
                </div>

                <div className="my-2.5">
                  {/* Apply right aligned financial tabular figures */}
                  <div className="text-xl font-bold font-mono text-on-surface tracking-tight truncate">
                    {card.value}
                  </div>
                </div>

                <div className="flex justify-between items-center mt-1 border-t border-outline-variant/30 pt-2">
                  <span className="text-[9px] text-outline font-semibold">vs prev. period</span>
                  <Sparkline points={card.sparkline} />
                </div>
              </div>
            );
          });
        })()}
      </div>
    </div>
  );
}

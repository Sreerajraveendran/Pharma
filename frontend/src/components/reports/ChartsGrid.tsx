import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, BarChart, Bar, Legend
} from 'recharts';

export default function ChartsGrid({ chartsData }: { chartsData: any }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

      {/* Area Chart: Revenue trend */}
      <div className="bg-white border border-outline-variant rounded-xl p-4 lg:col-span-2 space-y-4">
        <div>
          <h3 className="text-xs font-black uppercase text-primary tracking-wide">Revenue & Tax Trend (Daily)</h3>
          <p className="text-[10px] text-on-surface-variant">Continuous gross payment values and tax accumulations.</p>
        </div>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartsData.revenue_trend} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="colorRev" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0052cc" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#0052cc" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="colorGst" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#006c47" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#006c47" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef0f1" />
              <XAxis dataKey="name" stroke="#737685" fontSize={10} tickLine={false} />
              <YAxis stroke="#737685" fontSize={10} tickLine={false} />
              <Tooltip formatter={(value) => [`₹${value.toLocaleString()}`, '']} />
              <Legend verticalAlign="top" height={36} iconType="circle" />
              <Area name="Total Payments" type="monotone" dataKey="revenue" stroke="#0052cc" strokeWidth={2} fillOpacity={1} fill="url(#colorRev)" />
              <Area name="GST Collection" type="monotone" dataKey="gst" stroke="#006c47" strokeWidth={2} fillOpacity={1} fill="url(#colorGst)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Pie Chart: Payment Method distribution */}
      <div className="bg-white border border-outline-variant rounded-xl p-4 space-y-4">
        <div>
          <h3 className="text-xs font-black uppercase text-primary tracking-wide">Payment Distributions</h3>
          <p className="text-[10px] text-on-surface-variant">Breakdown of gross collection across transaction channels.</p>
        </div>
        <div className="h-64 flex justify-center items-center">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartsData.payment_distribution}
                innerRadius={60}
                outerRadius={80}
                paddingAngle={4}
                dataKey="value"
              >
                {chartsData.payment_distribution.map((_: any, index: number) => {
                  const colors = ['#0052cc', '#9b51e0', '#27ae60', '#f2994a', '#eb5757', '#2d9cdb'];
                  return <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />;
                })}
              </Pie>
              <Tooltip formatter={(value) => `₹${value.toLocaleString()}`} />
              <Legend iconSize={8} iconType="circle" layout="horizontal" verticalAlign="bottom" wrapperStyle={{ fontSize: '10px' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Bar Chart: Sales by Store */}
      <div className="bg-white border border-outline-variant rounded-xl p-4 space-y-4">
        <div>
          <h3 className="text-xs font-black uppercase text-primary tracking-wide">Sales by Store Outlet</h3>
          <p className="text-[10px] text-on-surface-variant">Revenue comparisons across pharmacy locations.</p>
        </div>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartsData.sales_by_store} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef0f1" />
              <XAxis dataKey="name" stroke="#737685" fontSize={9} tickLine={false} />
              <YAxis stroke="#737685" fontSize={10} tickLine={false} />
              <Tooltip formatter={(value) => `₹${value.toLocaleString()}`} />
              <Bar name="Sales Volume" dataKey="value" fill="#0052cc" radius={[4, 4, 0, 0]}>
                {chartsData.sales_by_store.map((_: any, index: number) => {
                  const colors = ['#0052cc', '#006c47', '#9b51e0'];
                  return <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />;
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Bar Chart: Insurance distribution */}
      <div className="bg-white border border-outline-variant rounded-xl p-4 space-y-4">
        <div>
          <h3 className="text-xs font-black uppercase text-primary tracking-wide">Insurance Provider Claims</h3>
          <p className="text-[10px] text-on-surface-variant">Gross volume processed per insurer provider.</p>
        </div>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartsData.insurance_distribution} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef0f1" />
              <XAxis dataKey="name" stroke="#737685" fontSize={9} tickLine={false} />
              <YAxis stroke="#737685" fontSize={10} tickLine={false} />
              <Tooltip formatter={(value) => `₹${value.toLocaleString()}`} />
              <Bar name="Claims Value" dataKey="value" fill="#9b51e0" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Top Selling Medicines */}
      <div className="bg-white border border-outline-variant rounded-xl p-4 space-y-4">
        <div>
          <h3 className="text-xs font-black uppercase text-primary tracking-wide">Top Selling Medicines</h3>
          <p className="text-[10px] text-on-surface-variant">High volume order fulfillment count.</p>
        </div>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartsData.top_medicines} layout="vertical" margin={{ top: 10, right: 10, left: -10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#eef0f1" />
              <XAxis type="number" stroke="#737685" fontSize={9} tickLine={false} />
              <YAxis type="category" dataKey="name" stroke="#737685" fontSize={9} tickLine={false} width={80} />
              <Tooltip />
              <Bar name="Units Sold" dataKey="value" fill="#006c47" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

    </div>
  );
}

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import Chart from 'chart.js/auto';
import '../style.css';

const emptyData = { drivers: [], work: [], expenses: [] };

const todayString = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
};

const defaultWorkForm = () => ({
  work_date: todayString(),
  driver_id: '',
  customer: '',
  location: '',
  hours: '',
  rate_per_hour: '',
  revenue: '',
  driver_earning: '',
  notes: ''
});

const formatINR = amount => `₹${Number(amount || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

function toDateOnly(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error(`The server returned an invalid date: ${value}`);
  }
  return parsed.toISOString().slice(0, 10);
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers
    }
  });
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error(`The server returned an invalid response (${response.status}).`);
  }
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status}).`);
  return result;
}

function toDriver(row) {
  return { ...row, type: row.rate_type, rate: Number(row.rate) };
}

function toWork(row) {
  return {
    ...row,
    date: toDateOnly(row.work_date),
    driverId: row.driver_id,
    hours: Number(row.hours),
    rate: Number(row.rate_per_hour),
    revenue: Number(row.revenue),
    driverEarning: Number(row.driver_earning)
  };
}

function toExpense(row) {
  return { ...row, date: toDateOnly(row.expense_date), type: row.expense_type, amount: Number(row.amount) };
}

async function getAllData() {
  const [drivers, work, expenses] = await Promise.all([
    apiRequest('/api/drivers'),
    apiRequest('/api/work'),
    apiRequest('/api/expenses')
  ]);
  return {
    drivers: drivers.map(toDriver),
    work: work.map(toWork),
    expenses: expenses.map(toExpense)
  };
}

function App() {
  const [data, setData] = useState(emptyData);
  const [page, setPage] = useState('dashboard');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [toast, setToast] = useState(null);
  const [saving, setSaving] = useState('');
  const [workForm, setWorkForm] = useState(defaultWorkForm);
  const chartCanvas = useRef(null);
  const chart = useRef(null);

  const notify = (message, isError = false) => setToast({ message, isError });

  useEffect(() => {
    if (!toast) return undefined;
    const timeout = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const initialData = await getAllData();
        if (!active) return;
        setData(initialData);
        setLoadError('');
      } catch (error) {
        if (active) {
          setLoadError(error.message);
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, []);

  const totals = useMemo(() => {
    const today = todayString();
    const now = new Date();
    const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const year = String(now.getFullYear());
    const result = {
      todayRevenue: 0, todayHours: 0, todayDriver: 0, todayExpenses: 0,
      monthRevenue: 0, monthDriver: 0, monthExpenses: 0,
      yearRevenue: 0, yearDriver: 0, yearExpenses: 0,
      totalRevenue: 0, totalDriver: 0, totalExpenses: 0
    };

    data.work.forEach(record => {
      result.totalRevenue += record.revenue;
      result.totalDriver += record.driverEarning;
      if (record.date === today) {
        result.todayRevenue += record.revenue;
        result.todayHours += record.hours;
        result.todayDriver += record.driverEarning;
      }
      if (record.date.startsWith(month)) {
        result.monthRevenue += record.revenue;
        result.monthDriver += record.driverEarning;
      }
      if (record.date.startsWith(year)) {
        result.yearRevenue += record.revenue;
        result.yearDriver += record.driverEarning;
      }
    });
    data.expenses.forEach(expense => {
      result.totalExpenses += expense.amount;
      if (expense.date === today) result.todayExpenses += expense.amount;
      if (expense.date.startsWith(month)) result.monthExpenses += expense.amount;
      if (expense.date.startsWith(year)) result.yearExpenses += expense.amount;
    });
    return result;
  }, [data]);

  useEffect(() => {
    if (page !== 'dashboard' || !chartCanvas.current) return undefined;
    const instance = new Chart(chartCanvas.current, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          label: 'Revenue (₹)',
          data: [],
          borderColor: '#f59e0b',
          backgroundColor: 'rgba(245, 158, 11, 0.1)',
          borderWidth: 3,
          fill: true,
          tension: 0.3
        }]
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: '#334155' }, ticks: { color: '#94a3b8' } },
          y: { grid: { color: '#334155' }, ticks: { color: '#94a3b8' }, beginAtZero: true }
        }
      }
    });
    chart.current = instance;
    return () => {
      instance.destroy();
      if (chart.current === instance) chart.current = null;
    };
  }, [page]);

  useEffect(() => {
    if (page !== 'dashboard' || !chart.current) return;
    const labels = [];
    const points = [];
    for (let offset = 6; offset >= 0; offset--) {
      const day = new Date();
      day.setDate(day.getDate() - offset);
      const date = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
      labels.push(day.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' }));
      points.push(data.work
        .filter(record => record.date === date)
        .reduce((sum, record) => sum + record.revenue, 0));
    }
    chart.current.data.labels = labels;
    chart.current.data.datasets[0].data = points;
    chart.current.update('none');
  }, [data.work, page]);

  async function reloadData() {
    setLoading(true);
    setLoadError('');
    try {
      setData(await getAllData());
    } catch (error) {
      setLoadError(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function saveRecord(key, url, payload, normalize, successMessage) {
    setSaving(key);
    try {
      const saved = normalize(await apiRequest(url, {
        method: 'POST',
        body: JSON.stringify(payload)
      }));
      setData(current => ({
        ...current,
        [key]: [saved, ...current[key]].sort((a, b) =>
          (b.date || '').localeCompare(a.date || '') || b.id - a.id
        )
      }));
      notify(successMessage);
      return true;
    } catch (error) {
      notify(error.message, true);
      return false;
    } finally {
      setSaving('');
    }
  }

  async function deleteRecord(type, id) {
    const endpoints = { work: '/api/work', drivers: '/api/drivers', expenses: '/api/expenses' };
    try {
      await apiRequest(`${endpoints[type]}/${id}`, { method: 'DELETE' });
      setData(current => ({
        ...current,
        [type]: current[type].filter(record => record.id !== id),
        ...(type === 'drivers' ? {
          work: current.work.map(record => record.driverId === id ? { ...record, driverId: null } : record)
        } : {})
      }));
      notify('Record deleted from PostgreSQL.');
    } catch (error) {
      notify(error.message, true);
    }
  }

  function updateWorkField(event) {
    const { name, value } = event.target;
    setWorkForm(current => {
      const updated = { ...current, [name]: value };
      if (name === 'hours' || name === 'rate_per_hour') {
        updated.revenue = String((Number(updated.hours) || 0) * (Number(updated.rate_per_hour) || 0));
      }
      if (name === 'hours' || name === 'driver_id') {
        const driver = data.drivers.find(item => item.id === Number(updated.driver_id));
        updated.driver_earning = driver
          ? String(driver.type === 'daily' ? driver.rate : (Number(updated.hours) || 0) * driver.rate)
          : '';
      }
      return updated;
    });
  }

  async function submitWork(event) {
    event.preventDefault();
    const saved = await saveRecord('work', '/api/work', {
      ...workForm,
      driver_id: workForm.driver_id ? Number(workForm.driver_id) : null,
      hours: Number(workForm.hours),
      rate_per_hour: Number(workForm.rate_per_hour),
      revenue: Number(workForm.revenue) || 0,
      driver_earning: Number(workForm.driver_earning) || 0
    }, toWork, 'Work record saved to PostgreSQL.');
    if (saved) setWorkForm(defaultWorkForm());
  }

  async function submitDriver(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const saved = await saveRecord('drivers', '/api/drivers', {
      name: form.get('name'),
      phone: form.get('phone'),
      rate_type: form.get('rate_type'),
      rate: Number(form.get('rate')) || 0
    }, toDriver, 'Driver saved to PostgreSQL.');
    if (saved) formElement.reset();
  }

  async function submitExpense(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const saved = await saveRecord('expenses', '/api/expenses', {
      expense_date: form.get('expense_date'),
      expense_type: form.get('expense_type'),
      amount: Number(form.get('amount')),
      description: form.get('description')
    }, toExpense, 'Expense saved to PostgreSQL.');
    if (saved) formElement.reset();
  }

  const pageTitles = {
    dashboard: 'Dashboard',
    work: 'Daily Work',
    drivers: 'Drivers',
    expenses: 'Expenses',
    reports: 'Reports'
  };
  const pageIcons = {
    dashboard: '⌂',
    work: '▣',
    drivers: '♙',
    expenses: '₹',
    reports: '▥'
  };
  const todayLabel = new Date().toLocaleDateString('en-IN', {
    weekday: 'long', year: 'numeric', month: 'short', day: 'numeric'
  });
  
  const driverTotals = new Map();
  data.work.forEach(record => {
    const current = driverTotals.get(record.driverId) || { hours: 0, earnings: 0 };
    current.hours += record.hours;
    current.earnings += record.driverEarning;
    driverTotals.set(record.driverId, current);
  });

  if (loading) {
    return <main className="loading-screen">Loading saved records…</main>;
  }
  if (loadError) {
    return (
      <main className="loading-screen">
        <p>Could not load saved records: {loadError}</p>
        <button className="primary" onClick={reloadData}>Try again</button>
      </main>
    );
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>🚜 JCB Manager</h1>
        <p className="muted">Work &amp; Revenue</p>
        <nav>
          {Object.entries(pageTitles).map(([key, title]) => (
            <button
              key={key}
              className={`nav-btn${page === key ? ' active' : ''}`}
              onClick={() => setPage(key)}
              aria-current={page === key ? 'page' : undefined}
            >
              <span className="nav-icon" aria-hidden="true">{pageIcons[key]}</span>
              <span>{title}</span>
            </button>
          ))}
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h2>{pageTitles[page]}</h2>
            <p className="muted">Track your JCB business operations in one place.</p>
          </div>
          <div className="account-menu">
            <span className="muted topbar-date">{todayLabel}</span>
          </div>
        </header>

        {page === 'dashboard' && (
          <section className="page active">
            <div className="cards">
              <Metric title="Today's Revenue" value={formatINR(totals.todayRevenue)} />
              <Metric title="Today's Work" value={`${totals.todayHours} hrs`} />
              <Metric title="Driver Earnings" value={formatINR(totals.todayDriver)} />
              <Metric title="Today's Profit" value={formatINR(totals.todayRevenue - totals.todayDriver - totals.todayExpenses)} />
              <Metric title="Monthly Revenue" value={formatINR(totals.monthRevenue)} />
              <Metric title="Monthly Profit" value={formatINR(totals.monthRevenue - totals.monthDriver - totals.monthExpenses)} />
              <Metric title="Yearly Revenue" value={formatINR(totals.yearRevenue)} />
              <Metric title="Total Revenue" value={formatINR(totals.totalRevenue)} />
            </div>
            <div className="grid2">
              <div className="panel">
                <h3>Last 7 Days Revenue</h3>
                <canvas ref={chartCanvas} />
              </div>
              <div className="panel">
                <h3>Driver Earnings</h3>
                {data.drivers.map(driver => (
                  <div className="driver-summary-row" key={driver.id}>
                    <span>{driver.name}</span><b>{formatINR(driverTotals.get(driver.id)?.earnings || 0)}</b>
                  </div>
                ))}
                {!data.drivers.length && <p className="muted">No earnings data available.</p>}
              </div>
            </div>
          </section>
        )}

        {page === 'work' && (
          <section className="page active">
            <div className="panel">
              <h3>Add Daily JCB Work</h3>
              <form className="form-grid" onSubmit={submitWork}>
                <label>Date<input type="date" name="work_date" value={workForm.work_date} onChange={updateWorkField} required /></label>
                <label>Driver
                  <select name="driver_id" value={workForm.driver_id} onChange={updateWorkField}>
                    <option value="">No driver</option>
                    {data.drivers.map(driver => <option key={driver.id} value={driver.id}>{driver.name}</option>)}
                  </select>
                </label>
                <label>Customer<input name="customer" value={workForm.customer} onChange={updateWorkField} placeholder="Customer name" /></label>
                <label>Location<input name="location" value={workForm.location} onChange={updateWorkField} placeholder="Work location" /></label>
                <label>Hours<input type="number" name="hours" min="0" step="0.5" value={workForm.hours} onChange={updateWorkField} required /></label>
                <label>Rate / Hour (₹)<input type="number" name="rate_per_hour" min="0" step="0.01" value={workForm.rate_per_hour} onChange={updateWorkField} required /></label>
                <label>Revenue (₹)<input type="number" name="revenue" min="0" step="0.01" value={workForm.revenue} onChange={updateWorkField} /></label>
                <label>Driver Earning (₹)<input type="number" name="driver_earning" min="0" step="0.01" value={workForm.driver_earning} onChange={updateWorkField} /></label>
                <label className="full">Notes<textarea name="notes" value={workForm.notes} onChange={updateWorkField} placeholder="Optional notes" /></label>
                <div className="full"><button className="primary" type="submit" disabled={saving === 'work'}>{saving === 'work' ? 'Saving…' : 'Save Work'}</button></div>
              </form>
            </div>
            <div className="panel">
              <h3>Work History</h3>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Date</th><th>Driver</th><th>Customer</th><th>Hours</th><th>Revenue</th><th>Driver Pay</th><th /></tr></thead>
                  <tbody>
                    {data.work.map(record => (
                      <tr key={record.id}>
                        <td data-label="Date">{record.date}</td>
                        <td data-label="Driver">{data.drivers.find(driver => driver.id === record.driverId)?.name || 'Unknown'}</td>
                        <td data-label="Customer">{record.customer || '-'}</td>
                        <td data-label="Hours">{record.hours} hrs</td>
                        <td data-label="Revenue">{formatINR(record.revenue)}</td>
                        <td data-label="Driver Pay">{formatINR(record.driverEarning)}</td>
                        <td className="row-action"><button className="action-btn" onClick={() => deleteRecord('work', record.id)} aria-label="Delete work record">✕</button></td>
                      </tr>
                    ))}
                    {!data.work.length && <EmptyRow columns={7}>No work records found.</EmptyRow>}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}

        {page === 'drivers' && (
          <section className="page active">
            <div className="panel">
              <h3>Add Driver</h3>
              <form className="form-grid" onSubmit={submitDriver}>
                <label>Name<input name="name" required /></label>
                <label>Phone<input name="phone" /></label>
                <label>Payment Type<select name="rate_type"><option value="daily">Daily</option><option value="hourly">Hourly</option></select></label>
                <label>Default Rate (₹)<input type="number" name="rate" min="0" step="0.01" /></label>
                <div className="full"><button className="primary" type="submit" disabled={saving === 'drivers'}>{saving === 'drivers' ? 'Saving…' : 'Add Driver'}</button></div>
              </form>
            </div>
            <div className="panel">
              <h3>Drivers</h3>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Name</th><th>Phone</th><th>Type</th><th>Rate</th><th>Total Hours</th><th>Total Earnings</th><th /></tr></thead>
                  <tbody>
                    {data.drivers.map(driver => {
                      const stats = driverTotals.get(driver.id) || { hours: 0, earnings: 0 };
                      return (
                        <tr key={driver.id}>
                          <td data-label="Name">{driver.name}</td><td data-label="Phone">{driver.phone || '-'}</td><td data-label="Type" className="capitalize">{driver.type}</td>
                          <td data-label="Rate">{formatINR(driver.rate)}</td><td data-label="Total Hours">{stats.hours} hrs</td><td data-label="Total Earnings">{formatINR(stats.earnings)}</td>
                          <td className="row-action"><button className="action-btn" onClick={() => deleteRecord('drivers', driver.id)} aria-label="Delete driver">✕</button></td>
                        </tr>
                      );
                    })}
                    {!data.drivers.length && <EmptyRow columns={7}>No drivers added yet.</EmptyRow>}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}

        {page === 'expenses' && (
          <section className="page active">
            <div className="panel">
              <h3>Add Expense</h3>
              <form className="form-grid" onSubmit={submitExpense}>
                <label>Date<input type="date" name="expense_date" defaultValue={todayString()} required /></label>
                <label>Type<select name="expense_type"><option>Fuel</option><option>Maintenance</option><option>Repair</option><option>Other</option></select></label>
                <label>Amount (₹)<input type="number" name="amount" min="0" step="0.01" required /></label>
                <label>Description<input name="description" placeholder="e.g. Engine oil change" /></label>
                <div className="full"><button className="primary" type="submit" disabled={saving === 'expenses'}>{saving === 'expenses' ? 'Saving…' : 'Save Expense'}</button></div>
              </form>
            </div>
            <div className="panel">
              <h3>Expense History</h3>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Date</th><th>Type</th><th>Amount</th><th>Description</th><th /></tr></thead>
                  <tbody>
                    {data.expenses.map(expense => (
                      <tr key={expense.id}>
                        <td data-label="Date">{expense.date}</td><td data-label="Type"><span className="expense-badge">{expense.type}</span></td>
                        <td data-label="Amount">{formatINR(expense.amount)}</td><td data-label="Description">{expense.description || '-'}</td>
                        <td className="row-action"><button className="action-btn" onClick={() => deleteRecord('expenses', expense.id)} aria-label="Delete expense">✕</button></td>
                      </tr>
                    ))}
                    {!data.expenses.length && <EmptyRow columns={5}>No expenses recorded.</EmptyRow>}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}

        {page === 'reports' && (
          <section className="page active">
            <div className="panel">
              <h3>Business Summary</h3>
              <div className="report-grid">
                <ReportValue title="Year Revenue" value={formatINR(totals.yearRevenue)} />
                <ReportValue title="Year Driver Earnings" value={formatINR(totals.yearDriver)} />
                <ReportValue title="Year Expenses" value={formatINR(totals.yearExpenses)} />
                <ReportValue title="Year Profit" value={formatINR(totals.yearRevenue - totals.yearDriver - totals.yearExpenses)} />
                <ReportValue title="Total Revenue" value={formatINR(totals.totalRevenue)} />
                <ReportValue title="Total Profit" value={formatINR(totals.totalRevenue - totals.totalDriver - totals.totalExpenses)} />
              </div>
            </div>
          </section>
        )}
      </main>

      {toast && <div id="toast" className="show" role="status" style={{ backgroundColor: toast.isError ? 'var(--danger)' : 'var(--success)' }}>{toast.message}</div>}
    </div>
  );
}

function Metric({ title, value }) {
  return <div className="card"><span>{title}</span><strong>{value}</strong></div>;
}

function ReportValue({ title, value }) {
  return <div><span>{title}</span><b>{value}</b></div>;
}

function EmptyRow({ columns, children }) {
  return <tr><td colSpan={columns} className="empty-row">{children}</td></tr>;
}

createRoot(document.getElementById('root')).render(<App />);
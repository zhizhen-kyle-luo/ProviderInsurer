import { useState } from 'react';
import { Upload, FileJson, AlertCircle } from 'lucide-react';
import { AuditLog } from './types/audit';
import { loadAuditLog } from './utils/dataLoader';
import { Timeline } from './components/Timeline';

function App() {
  const [auditLog, setAuditLog] = useState<AuditLog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setLoading(true);
    setError(null);

    try {
      const log = await loadAuditLog(file);
      setAuditLog(log);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load audit log');
    } finally {
      setLoading(false);
    }
  };

  const handleDrop = async (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (!file) return;

    setLoading(true);
    setError(null);

    try {
      const log = await loadAuditLog(file);
      setAuditLog(log);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load audit log');
    } finally {
      setLoading(false);
    }
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      {/* header */}
      <header className="bg-white border-b border-slate-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-slate-900">Audit Log Viewer</h1>
              <p className="text-sm text-slate-600 mt-1">
                Multi-Agent Healthcare Simulation Debug Tool
              </p>
            </div>
            {auditLog && (
              <div className="text-right">
                <div className="text-sm font-medium text-slate-700">{auditLog.case_id}</div>
                <div className="text-xs text-slate-500">
                  {auditLog.interactions.length} interactions
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* main content */}
      <main className="max-w-7xl mx-auto px-4 py-8">
        {!auditLog ? (
          <div className="flex flex-col items-center justify-center min-h-[60vh]">
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              className="w-full max-w-2xl"
            >
              <div className="border-2 border-dashed border-slate-300 rounded-lg p-12 text-center hover:border-blue-400 hover:bg-blue-50 transition-colors cursor-pointer">
                <FileJson className="w-16 h-16 mx-auto text-slate-400 mb-4" />
                <h3 className="text-lg font-semibold text-slate-700 mb-2">
                  Load Audit Log
                </h3>
                <p className="text-sm text-slate-500 mb-6">
                  Drag and drop a JSON audit log file here, or click to browse
                </p>
                <label className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors cursor-pointer">
                  <Upload className="w-5 h-5" />
                  Choose File
                  <input
                    type="file"
                    accept=".json"
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                </label>
              </div>
            </div>

            {error && (
              <div className="mt-6 max-w-2xl w-full bg-red-50 border border-red-200 rounded-lg p-4">
                <div className="flex items-center gap-2 text-red-800">
                  <AlertCircle className="w-5 h-5" />
                  <span className="font-medium">Error loading file:</span>
                </div>
                <p className="text-sm text-red-700 mt-2">{error}</p>
              </div>
            )}

            {loading && (
              <div className="mt-6 text-slate-600">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                <p className="text-sm text-center mt-2">Loading audit log...</p>
              </div>
            )}
          </div>
        ) : (
          <div>
            {/* summary card */}
            <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6 mb-8">
              <h2 className="text-lg font-semibold text-slate-900 mb-4">Simulation Summary</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div>
                  <div className="text-slate-600 mb-1">Start Time</div>
                  <div className="font-medium text-slate-900">
                    {new Date(auditLog.simulation_start).toLocaleString()}
                  </div>
                </div>
                {auditLog.simulation_end && (
                  <div>
                    <div className="text-slate-600 mb-1">End Time</div>
                    <div className="font-medium text-slate-900">
                      {new Date(auditLog.simulation_end).toLocaleString()}
                    </div>
                  </div>
                )}
                <div>
                  <div className="text-slate-600 mb-1">Total Interactions</div>
                  <div className="font-medium text-slate-900">
                    {auditLog.interactions.length}
                  </div>
                </div>
                {auditLog.summary?.interactions_by_agent && (
                  <div>
                    <div className="text-slate-600 mb-1">By Agent</div>
                    <div className="font-medium text-slate-900">
                      {Object.entries(auditLog.summary.interactions_by_agent).map(
                        ([agent, count]) => (
                          <div key={agent} className="text-xs">
                            {agent}: {count as number}
                          </div>
                        )
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* reload button */}
              <div className="mt-6 pt-4 border-t border-slate-200">
                <label className="inline-flex items-center gap-2 px-4 py-2 bg-slate-100 text-slate-700 rounded-lg font-medium hover:bg-slate-200 transition-colors cursor-pointer text-sm">
                  <Upload className="w-4 h-4" />
                  Load Different Log
                  <input
                    type="file"
                    accept=".json"
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                </label>
              </div>
            </div>

            {/* timeline */}
            <Timeline interactions={auditLog.interactions} />
          </div>
        )}
      </main>
    </div>
  );
}

export default App;

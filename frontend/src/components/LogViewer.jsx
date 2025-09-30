import React, { useState, useEffect } from 'react';
import { Card, Select, Input, Tag, List, Alert } from 'antd';

const { Option } = Select;
const { Search } = Input;

const LogViewer = () => {
    const [entries, setEntries] = useState([]);
    const [filters, setFilters] = useState({
        operation: '',
        level: '',
        resourceType: '',
        search: ''
    });
    const [statistics, setStatistics] = useState({});

    const loadLogs = async () => {
        const queryParams = new URLSearchParams();
        Object.entries(filters).forEach(([key, value]) => {
          if (value) queryParams.append(key, value);
        });
      
        try {
          const response = await fetch(`http://localhost:8000/api/v2/entries?${queryParams}`);
          if (!response.ok) {
            throw new Error(`Failed to load logs: ${response.status}`);
          }
          const data = await response.json();
          setEntries(data);
        } catch (error) {
          console.error('Failed to load logs:', error);
          // Можно добавить уведомление об ошибке
        }
    };

    const loadStatistics = async () => {
        try {
          const response = await fetch('http://localhost:8000/api/v2/statistics');
          if (!response.ok) {
            throw new Error(`Failed to load statistics: ${response.status}`);
          }
          const data = await response.json();
          setStatistics(data);
        } catch (error) {
          console.error('Failed to load statistics:', error);
        }
    };

    useEffect(() => {
        loadLogs();
        loadStatistics();
    }, [filters]);

    const getLevelColor = (level) => {
        const colors = {
            error: 'red',
            warn: 'orange',
            info: 'blue',
            debug: 'gray',
            trace: 'lightgray'
        };
        return colors[level] || 'black';
    };

    return (
        <div className="log-viewer">
            <Card title="📊 Terraform Log Viewer">
                {/* Фильтры */}
                <div className="filters">
                    <Select 
                        value={filters.operation} 
                        onChange={value => setFilters({...filters, operation: value})}
                        placeholder="Operation"
                        style={{ width: 150 }}
                        allowClear
                    >
                        <Option value="plan">Plan</Option>
                        <Option value="apply">Apply</Option>
                        <Option value="validate">Validate</Option>
                    </Select>

                    <Select 
                        value={filters.level}
                        onChange={value => setFilters({...filters, level: value})}
                        placeholder="Log Level"
                        style={{ width: 150 }}
                        allowClear
                    >
                        <Option value="error">Error</Option>
                        <Option value="warn">Warning</Option>
                        <Option value="info">Info</Option>
                        <Option value="debug">Debug</Option>
                        <Option value="trace">Trace</Option>
                    </Select>

                    <Search
                        placeholder="Search messages..."
                        value={filters.search}
                        onChange={e => setFilters({...filters, search: e.target.value})}
                        style={{ width: 300 }}
                    />
                </div>

                {/* Статистика */}
                {statistics.total_entries && (
                    <div className="statistics">
                        <h3>Operations Summary</h3>
                        <p><strong>Total Entries:</strong> {statistics.total_entries}</p>
                        {Object.entries(statistics.operations || {}).map(([op, count]) => (
                            <div key={op} className="op-stats">
                                <strong>{op.toUpperCase()}:</strong> {count} entries
                            </div>
                        ))}
                    </div>
                )}

                {/* Таблица логов */}
                <List
                    dataSource={entries}
                    renderItem={entry => (
                        <List.Item>
                            <div className={`log-entry level-${entry.level}`} style={{ width: '100%' }}>
                                <div className="entry-header">
                                    <span className="timestamp">
                                        {new Date(entry.timestamp).toLocaleString()}
                                    </span>
                                    <Tag color={getLevelColor(entry.level)}>
                                        {entry.level}
                                    </Tag>
                                    <span className="operation">{entry.operation}</span>
                                    {entry.tf_req_id && (
                                        <span className="req-id">Req: {entry.tf_req_id}</span>
                                    )}
                                </div>
                                <div style={{ marginBottom: 8 }}>{entry.message}</div>
                                {entry.tf_resource_type && (
                                    <Tag>Resource: {entry.tf_resource_type}</Tag>
                                )}
                                {entry.tf_rpc && (
                                    <Tag color="purple">RPC: {entry.tf_rpc}</Tag>
                                )}
                            </div>
                        </List.Item>
                    )}
                />

                {entries.length === 0 && (
                    <Alert 
                        message="No logs found" 
                        description="Upload some Terraform logs first or adjust your filters"
                        type="info"
                        showIcon
                    />
                )}
            </Card>
        </div>
    );
};

export default LogViewer;
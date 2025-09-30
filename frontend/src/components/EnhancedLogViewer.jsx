import React, { useState, useEffect } from 'react';
import { Card, Select, Input, Tag, List, Alert, Collapse, Button, Checkbox, Row, Col, message } from 'antd';
import { CaretRightOutlined, CaretDownOutlined, CheckOutlined, EyeOutlined, CodeOutlined } from '@ant-design/icons';

const { Option } = Select;
const { Search } = Input;
const { Panel } = Collapse;

const EnhancedLogViewer = () => {
    const [entries, setEntries] = useState([]);
    const [groupedEntries, setGroupedEntries] = useState({});
    const [expandedGroups, setExpandedGroups] = useState(new Set());
    const [expandedJsonBlocks, setExpandedJsonBlocks] = useState(new Set());
    const [filters, setFilters] = useState({
        operation: '',
        level: '',
        resourceType: '',
        search: '',
        showRead: true
    });
    const [statistics, setStatistics] = useState({});

    const loadLogs = async () => {
        const queryParams = new URLSearchParams();
        Object.entries(filters).forEach(([key, value]) => {
            if (value && key !== 'showRead') queryParams.append(key, value);
        });

        try {
            const response = await fetch(`http://localhost:8000/api/v2/entries?${queryParams}`);
            const data = await response.json();
            setEntries(data);
            groupEntries(data);
        } catch (error) {
            console.error('Failed to load logs:', error);
        }
    };

    const loadStatistics = async () => {
        try {
            const response = await fetch('http://localhost:8000/api/v2/statistics');
            const data = await response.json();
            setStatistics(data);
        } catch (error) {
            console.error('Failed to load statistics:', error);
        }
    };

    const groupEntries = (entries) => {
        const grouped = entries.reduce((acc, entry) => {
            const groupId = entry.tf_req_id || 'ungrouped';
            if (!acc[groupId]) acc[groupId] = [];
            acc[groupId].push(entry);
            return acc;
        }, {});
        setGroupedEntries(grouped);
    };

    useEffect(() => {
        loadLogs();
        loadStatistics();
    }, [filters]);

    const markAsRead = async (entryId) => {
        try {
            await fetch(`http://localhost:8000/api/v2/entries/${entryId}/read`, { method: 'POST' });
            // Обновляем локальное состояние
            setEntries(prev => prev.map(entry => 
                entry.id === entryId ? { ...entry, read: true } : entry
            ));
            message.success('Marked as read');
        } catch (error) {
            console.error('Failed to mark as read:', error);
            message.error('Failed to mark as read');
        }
    };

    const toggleGroup = (groupId) => {
        setExpandedGroups(prev => {
            const newSet = new Set(prev);
            if (newSet.has(groupId)) {
                newSet.delete(groupId);
            } else {
                newSet.add(groupId);
            }
            return newSet;
        });
    };

    const toggleJsonBlock = (blockId) => {
        setExpandedJsonBlocks(prev => {
            const newSet = new Set(prev);
            if (newSet.has(blockId)) {
                newSet.delete(blockId);
            } else {
                newSet.add(blockId);
            }
            return newSet;
        });
    };

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

    const getOperationColor = (operation) => {
        const colors = {
            plan: 'blue',
            apply: 'green',
            validate: 'orange',
            unknown: 'gray'
        };
        return colors[operation] || 'gray';
    };

    const renderJsonBlock = (jsonBlock, entryId, blockIndex) => {
        const blockId = `${entryId}-${blockIndex}`;
        const isExpanded = expandedJsonBlocks.has(blockId);

        return (
            <div key={blockIndex} style={{ marginTop: 8 }}>
                <Button 
                    type="link" 
                    icon={isExpanded ? <CaretDownOutlined /> : <CaretRightOutlined />}
                    onClick={() => toggleJsonBlock(blockId)}
                    style={{ padding: 0, height: 'auto' }}
                >
                    <CodeOutlined /> {jsonBlock.type} {jsonBlock.raw ? '(raw)' : ''}
                </Button>
                {isExpanded && (
                    <Collapse defaultActiveKey="1" style={{ marginTop: 8 }}>
                        <Panel header="JSON Data" key="1">
                            <pre style={{ 
                                background: '#f5f5f5', 
                                padding: '12px', 
                                borderRadius: '4px',
                                fontSize: '12px',
                                maxHeight: '400px',
                                overflow: 'auto'
                            }}>
                                {JSON.stringify(jsonBlock.data, null, 2)}
                            </pre>
                        </Panel>
                    </Collapse>
                )}
            </div>
        );
    };

    return (
        <div className="log-viewer">
            <Card title="📊 Enhanced Terraform Log Viewer" extra={
                <Button onClick={loadLogs}>Refresh</Button>
            }>
                {/* Улучшенные фильтры */}
                <Row gutter={16} style={{ marginBottom: 16 }}>
                    <Col span={4}>
                        <Select 
                            value={filters.operation} 
                            onChange={value => setFilters({...filters, operation: value})}
                            placeholder="Operation"
                            style={{ width: '100%' }}
                            allowClear
                        >
                            <Option value="plan">Plan</Option>
                            <Option value="apply">Apply</Option>
                            <Option value="validate">Validate</Option>
                            <Option value="unknown">Unknown</Option>
                        </Select>
                    </Col>
                    <Col span={4}>
                        <Select 
                            value={filters.level}
                            onChange={value => setFilters({...filters, level: value})}
                            placeholder="Log Level"
                            style={{ width: '100%' }}
                            allowClear
                        >
                            <Option value="error">Error</Option>
                            <Option value="warn">Warning</Option>
                            <Option value="info">Info</Option>
                            <Option value="debug">Debug</Option>
                            <Option value="trace">Trace</Option>
                        </Select>
                    </Col>
                    <Col span={8}>
                        <Search
                            placeholder="Search messages, resources, RPC..."
                            value={filters.search}
                            onChange={e => setFilters({...filters, search: e.target.value})}
                            style={{ width: '100%' }}
                        />
                    </Col>
                    <Col span={4}>
                        <Checkbox
                            checked={filters.showRead}
                            onChange={e => setFilters({...filters, showRead: e.target.checked})}
                        >
                            Show Read
                        </Checkbox>
                    </Col>
                    <Col span={4}>
                        <Tag color="blue">Total: {entries.length}</Tag>
                    </Col>
                </Row>

                {/* Статистика */}
                {statistics.total_entries > 0 && (
                    <Alert
                        message={`Processed ${statistics.total_entries} log entries with ${statistics.json_blocks_count || 0} JSON blocks`}
                        description={`Operations: ${Object.keys(statistics.operations || {}).join(', ')} | Levels: ${Object.keys(statistics.levels || {}).join(', ')}`}
                        type="info"
                        style={{ marginBottom: 16 }}
                    />
                )}

                {/* Группировка по tf_req_id */}
                <div className="log-groups">
                    {Object.entries(groupedEntries).map(([groupId, groupEntries]) => (
                        <Card 
                            key={groupId} 
                            size="small" 
                            title={
                                <div 
                                    style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}
                                    onClick={() => toggleGroup(groupId)}
                                >
                                    {expandedGroups.has(groupId) ? <CaretDownOutlined /> : <CaretRightOutlined />}
                                    <span>
                                        {groupId === 'ungrouped' ? 'Ungrouped Entries' : `Request Group: ${groupId}`}
                                    </span>
                                    <Tag color="blue">{groupEntries.length} entries</Tag>
                                    {groupId !== 'ungrouped' && (
                                        <Tag color={getOperationColor(groupEntries[0]?.operation)}>
                                            {groupEntries[0]?.operation}
                                        </Tag>
                                    )}
                                </div>
                            }
                            style={{ marginBottom: 16 }}
                        >
                            {expandedGroups.has(groupId) && (
                                <List
                                    dataSource={groupEntries}
                                    renderItem={entry => (
                                        <List.Item>
                                            <div className={`log-entry level-${entry.level}`} style={{ 
                                                width: '100%',
                                                opacity: entry.read ? 0.6 : 1,
                                                background: entry.read ? '#fafafa' : 'white'
                                            }}>
                                                <div className="entry-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                                        <span className="timestamp" style={{ color: '#666', fontSize: '0.9em' }}>
                                                            {new Date(entry.timestamp).toLocaleString()}
                                                        </span>
                                                        <Tag color={getLevelColor(entry.level)}>
                                                            {entry.level}
                                                        </Tag>
                                                        <Tag color={getOperationColor(entry.operation)}>
                                                            {entry.operation}
                                                        </Tag>
                                                        {entry.tf_resource_type && (
                                                            <Tag>Resource: {entry.tf_resource_type}</Tag>
                                                        )}
                                                        {entry.tf_rpc && (
                                                            <Tag color="purple">RPC: {entry.tf_rpc}</Tag>
                                                        )}
                                                    </div>
                                                    <Button 
                                                        type="text" 
                                                        icon={entry.read ? <CheckOutlined /> : <EyeOutlined />}
                                                        onClick={() => markAsRead(entry.id)}
                                                        title={entry.read ? "Mark as unread" : "Mark as read"}
                                                    />
                                                </div>
                                                
                                                <div style={{ marginBottom: 8, fontFamily: 'monospace' }}>
                                                    {entry.message}
                                                </div>
                                                
                                                {/* JSON блоки */}
                                                {entry.json_blocks && entry.json_blocks.map((jsonBlock, idx) => (
                                                    renderJsonBlock(jsonBlock, entry.id, idx)
                                                ))}
                                            </div>
                                        </List.Item>
                                    )}
                                />
                            )}
                        </Card>
                    ))}
                </div>

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

export default EnhancedLogViewer;
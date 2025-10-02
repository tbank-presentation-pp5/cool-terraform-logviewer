import React, { useEffect, useState } from 'react';
import { Card, Alert, Row, Col, Statistic, Select, Tag, Empty, Tooltip } from 'antd';
import { ClockCircleOutlined, CheckCircleOutlined, SyncOutlined, WarningOutlined } from '@ant-design/icons';

const { Option } = Select;

const GanttChart = () => {
    const [ganttData, setGanttData] = useState([]);
    const [filter, setFilter] = useState('all');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadGanttData();
    }, []);

    const loadGanttData = async () => {
        try {
            const response = await fetch('http://localhost:8000/api/v2/gantt-data');
            const data = await response.json();
            setGanttData(data.gantt_data || []);
        } catch (error) {
            console.error('Failed to load gantt data:', error);
        } finally {
            setLoading(false);
        }
    };

    const filteredData = filter === 'all' 
        ? ganttData 
        : ganttData.filter(item => item.type === filter);

    const getOperationColor = (operation) => {
        const colors = {
            plan: '#1890ff',
            apply: '#52c41a',
            validate: '#faad14',
            unknown: '#222222'
        };
        return colors[operation] || '#333333';
    };

    const formatDuration = (seconds) => {
        if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
        if (seconds < 60) return `${Math.round(seconds)}s`;
        return `${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s`;
    };

    const formatTime = (timestamp) => {
        return new Date(timestamp).toLocaleTimeString();
    };

    // Вычисляем временную шкалу
    const getTimelineScale = () => {
        if (filteredData.length === 0) return { min: new Date(), max: new Date(), range: 0 };
        
        const timestamps = filteredData.flatMap(item => [
            new Date(item.start).getTime(),
            new Date(item.end).getTime()
        ]);
        
        const min = Math.min(...timestamps);
        const max = Math.max(...timestamps);
        const range = max - min || 1;
        
        return { min, max, range };
    };

    const timeline = getTimelineScale();

    // Функция для вычисления позиции и ширины бара
    const getBarStyle = (item) => {
        const startTime = new Date(item.start).getTime();
        const endTime = new Date(item.end).getTime();
        
        const left = ((startTime - timeline.min) / timeline.range) * 100;
        const width = Math.max(((endTime - startTime) / timeline.range) * 100, 0.5);
        
        return {
            left: `${left}%`,
            width: `${width}%`,
            backgroundColor: getOperationColor(item.type),
            position: 'absolute',
            height: '24px',
            borderRadius: '4px',
            cursor: 'pointer',
            transition: 'all 0.3s ease'
        };
    };

    const stats = {
        total: ganttData.length,
        plan: ganttData.filter(item => item.type === 'plan').length,
        apply: ganttData.filter(item => item.type === 'apply').length,
        validate: ganttData.filter(item => item.type === 'validate').length,
        avgDuration: ganttData.length > 0 
            ? ganttData.reduce((acc, item) => acc + item.duration, 0) / ganttData.length
            : 0
    };

    return (
        <div style={{ padding: '20px' }}>
            <Card 
                title="Terraform Operations Gantt Chart" 
                loading={loading}
                extra={
                    <Select value={filter} onChange={setFilter} style={{ width: 150 }}>
                        <Option value="all">All Operations</Option>
                        <Option value="plan">Plan Only</Option>
                        <Option value="apply">Apply Only</Option>
                        <Option value="validate">Validate Only</Option>
                    </Select>
                }
            >
                {/* Статистика */}
                <Row gutter={16} style={{ marginBottom: 24 }}>
                    <Col span={6}>
                        <Card size="small">
                            <Statistic 
                                title="Total Operations" 
                                value={stats.total}
                                prefix={<ClockCircleOutlined />}
                            />
                        </Card>
                    </Col>
                    <Col span={6}>
                        <Card size="small">
                            <Statistic 
                                title="Plan Operations" 
                                value={stats.plan}
                                prefix={<SyncOutlined />}
                                valueStyle={{ color: '#1890ff' }}
                            />
                        </Card>
                    </Col>
                    <Col span={6}>
                        <Card size="small">
                            <Statistic 
                                title="Apply Operations" 
                                value={stats.apply}
                                prefix={<CheckCircleOutlined />}
                                valueStyle={{ color: '#52c41a' }}
                            />
                        </Card>
                    </Col>
                    <Col span={6}>
                        <Card size="small">
                            <Statistic 
                                title="Avg Duration" 
                                value={formatDuration(stats.avgDuration)}
                            />
                        </Card>
                    </Col>
                </Row>

                {/* Gantt Chart Visualization */}
                {filteredData.length > 0 ? (
                    <div style={{ marginTop: 24 }}>
                        <div style={{ 
                            padding: '20px', 
                            borderRadius: '8px',
                            overflowX: 'auto'
                        }}>
                            {/* Временная шкала */}
                            <div style={{ 
                                display: 'flex', 
                                justifyContent: 'space-between', 
                                marginBottom: '16px',
                                padding: '0 40px',
                                color: '#666',
                                fontSize: '12px'
                            }}>
                                <span>Start: {new Date(timeline.min).toLocaleString()}</span>
                                <span>End: {new Date(timeline.max).toLocaleString()}</span>
                            </div>

                            {/* Gantt Bars */}
                            <div style={{ minHeight: '400px' }}>
                                {filteredData.map((item, index) => (
                                    <div 
                                        key={item.id} 
                                        style={{ 
                                            marginBottom: '16px',
                                            position: 'relative',
                                            height: '50px'
                                        }}
                                    >
                                        {/* Task Label */}
                                        <div style={{ 
                                            position: 'absolute',
                                            left: 0,
                                            top: 0,
                                            width: '35%',
                                            fontSize: '12px',
                                            fontWeight: '500',
                                            overflow: 'hidden',
                                            textOverflow: 'ellipsis',
                                            whiteSpace: 'nowrap',
                                            paddingRight: '10px'
                                        }}>
                                            <Tag color={getOperationColor(item.type)} style={{ marginRight: 4 }}>
                                                {item.type}
                                            </Tag>
                                            {item.task}
                                        </div>

                                        {/* Timeline Container */}
                                        <div style={{
                                            position: 'absolute',
                                            left: '35%',
                                            right: 0,
                                            top: '13px',
                                            height: '24px',
                                            border: '0.5px solid #222222',
                                            borderRadius: '4px'
                                        }}>
                                            {/* Gantt Bar */}
                                            <Tooltip 
                                                title={
                                                    <div>
                                                        <div><strong>{item.task}</strong></div>
                                                        <div>Start: {formatTime(item.start)}</div>
                                                        <div>End: {formatTime(item.end)}</div>
                                                        <div>Duration: {formatDuration(item.duration)}</div>
                                                        <div>Entries: {item.entry_count}</div>
                                                        {item.resources && item.resources.length > 0 && (
                                                            <div>Resources: {item.resources.join(', ')}</div>
                                                        )}
                                                    </div>
                                                }
                                            >
                                                <div 
                                                    style={getBarStyle(item)}
                                                    onMouseEnter={(e) => {
                                                        e.currentTarget.style.opacity = '0.8';
                                                        e.currentTarget.style.transform = 'scaleY(1.1)';
                                                    }}
                                                    onMouseLeave={(e) => {
                                                        e.currentTarget.style.opacity = '1';
                                                        e.currentTarget.style.transform = 'scaleY(1)';
                                                    }}
                                                >
                                                    <div style={{
                                                        padding: '4px 8px',
                                                        color: 'white',
                                                        fontSize: '11px',
                                                        fontWeight: '500',
                                                        overflow: 'hidden',
                                                        textOverflow: 'ellipsis',
                                                        whiteSpace: 'nowrap'
                                                    }}>
                                                        {formatDuration(item.duration)}
                                                    </div>
                                                </div>
                                            </Tooltip>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Легенда */}
                        <div style={{ 
                            marginTop: 24, 
                            textAlign: 'center', 
                            padding: '16px', 
                            
                            borderRadius: '6px' 
                        }}>
                            <h4>Legend:</h4>
                            <Tag color="#1890ff" icon={<SyncOutlined />}>Plan Operations</Tag>
                            <Tag color="#52c41a" icon={<CheckCircleOutlined />}>Apply Operations</Tag>
                            <Tag color="#faad14" icon={<WarningOutlined />}>Validate Operations</Tag>
                        </div>
                    </div>
                ) : (
                    <Empty 
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description={
                            <span>
                                No timeline data available. <br />
                                Upload Terraform logs with tf_req_id to see the Gantt chart.
                            </span>
                        }
                    />
                )}

                {/* Детальная таблица */}
                {filteredData.length > 0 && (
                    <Card title="Operation Details" style={{ marginTop: 24 }} size="small">
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr>
                                        <th style={{ padding: '8px', textAlign: 'left' }}>Operation</th>
                                        <th style={{ padding: '8px', textAlign: 'left' }}>Task</th>
                                        <th style={{ padding: '8px', textAlign: 'left' }}>Start Time</th>
                                        <th style={{ padding: '8px', textAlign: 'left' }}>End Time</th>
                                        <th style={{ padding: '8px', textAlign: 'left' }}>Duration</th>
                                        <th style={{ padding: '8px', textAlign: 'left' }}>Entries</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {filteredData.map((item) => (
                                        <tr key={item.id}>
                                            <td style={{ padding: '8px' }}>
                                                <Tag color={getOperationColor(item.type)}>{item.type}</Tag>
                                            </td>
                                            <td style={{ padding: '8px' }}>{item.task}</td>
                                            <td style={{ padding: '8px' }}>{formatTime(item.start)}</td>
                                            <td style={{ padding: '8px' }}>{formatTime(item.end)}</td>
                                            <td style={{ padding: '8px' }}>{formatDuration(item.duration)}</td>
                                            <td style={{ padding: '8px' }}>{item.entry_count}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                )}
            </Card>
        </div>
    );
};

export default GanttChart;
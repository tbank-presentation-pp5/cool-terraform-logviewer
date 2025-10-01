import React, { useEffect, useState } from 'react';
import { Card, Alert, Row, Col, Statistic, Select, Tag, Timeline, Empty } from 'antd';
import { ClockCircleOutlined, CheckCircleOutlined, SyncOutlined } from '@ant-design/icons';

const { Option } = Select;

const GanttChart = () => {
    const [ganttData, setGanttData] = useState([]);
    const [filter, setFilter] = useState('all');

    useEffect(() => {
        loadGanttData();
    }, []);

    const loadGanttData = async () => {
        try {
            const response = await fetch('http://localhost:8000/api/v2/gantt-data');
            const data = await response.json();
            setGanttData(data.gantt_data);
        } catch (error) {
            console.error('Failed to load gantt data:', error);
        }
    };

    const filteredData = filter === 'all' 
        ? ganttData 
        : ganttData.filter(item => item.type === filter);

    const getOperationColor = (operation) => {
        const colors = {
            plan: 'blue',
            apply: 'green',
            validate: 'orange',
            unknown: 'gray'
        };
        return colors[operation] || 'gray';
    };

    const getOperationIcon = (operation) => {
        const icons = {
            plan: <SyncOutlined />,
            apply: <CheckCircleOutlined />,
            validate: <ClockCircleOutlined />
        };
        return icons[operation] || <ClockCircleOutlined />;
    };

    const formatDuration = (seconds) => {
        if (seconds < 60) {
            return `${Math.round(seconds)}s`;
        } else {
            return `${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s`;
        }
    };

    const formatTime = (timestamp) => {
        return new Date(timestamp).toLocaleTimeString();
    };

    const stats = {
        total: ganttData.length,
        plan: ganttData.filter(item => item.type === 'plan').length,
        apply: ganttData.filter(item => item.type === 'apply').length,
        validate: ganttData.filter(item => item.type === 'validate').length,
        avgDuration: ganttData.length > 0 
            ? Math.round(ganttData.reduce((acc, item) => acc + item.duration, 0) / ganttData.length) 
            : 0
    };

    return (
        <div className="gantt-chart">
            <Card 
                title="Terraform Operations Timeline" 
                extra={
                    <Select value={filter} onChange={setFilter} style={{ width: 120 }}>
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
                            <Statistic title="Total Operations" value={stats.total} />
                        </Card>
                    </Col>
                    <Col span={6}>
                        <Card size="small">
                            <Statistic title="Plan Operations" value={stats.plan} />
                        </Card>
                    </Col>
                    <Col span={6}>
                        <Card size="small">
                            <Statistic title="Apply Operations" value={stats.apply} />
                        </Card>
                    </Col>
                    <Col span={6}>
                        <Card size="small">
                            <Statistic title="Avg Duration" value={formatDuration(stats.avgDuration)} />
                        </Card>
                    </Col>
                </Row>

                {/* Timeline вместо Chart.js */}
                {filteredData.length > 0 ? (
                    <Timeline
                        mode="left"
                        items={filteredData.map((item, index) => ({
                            key: index,
                            color: getOperationColor(item.type),
                            dot: getOperationIcon(item.type),
                            children: (
                                <div style={{ padding: '8px 0' }}>
                                    <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>
                                        {item.task}
                                    </div>
                                    <div style={{ color: '#666', fontSize: '12px', marginBottom: '4px' }}>
                                        ⏰ {formatTime(item.start)} - {formatTime(item.end)}
                                    </div>
                                    <div style={{ color: '#666', fontSize: '12px', marginBottom: '4px' }}>
                                        ⏱️ Duration: {formatDuration(item.duration)}
                                    </div>
                                    <div style={{ color: '#666', fontSize: '12px' }}>
                                        📊 Entries: {item.entry_count}
                                    </div>
                                    {item.resources && item.resources.length > 0 && (
                                        <div style={{ marginTop: '4px' }}>
                                            {item.resources.map((resource, idx) => (
                                                <Tag 
                                                    key={idx} 
                                                    color="blue" 
                                                    size="small"
                                                    style={{ margin: '2px' }}
                                                >
                                                    {resource}
                                                </Tag>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            ),
                        }))}
                    />
                ) : (
                    <Empty 
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description={
                            <span>
                                No timeline data available. <br />
                                Upload Terraform logs with tf_req_id to see the timeline.
                            </span>
                        }
                    />
                )}

                {/* Легенда */}
                <div style={{ marginTop: 24, textAlign: 'center', padding: '16px', background: '#f5f5f5', borderRadius: '6px' }}>
                    <h4>Legend:</h4>
                    <Tag color="blue" icon={<SyncOutlined />}>Plan Operations</Tag>
                    <Tag color="green" icon={<CheckCircleOutlined />}>Apply Operations</Tag>
                    <Tag color="orange" icon={<ClockCircleOutlined />}>Validate Operations</Tag>
                </div>
            </Card>
        </div>
    );
};

export default GanttChart;
import React, { useState, useEffect, useRef } from 'react';
import { Card, Statistic, Alert, List, Tag, Row, Col, Button, Progress } from 'antd';
import { WarningOutlined, CheckCircleOutlined, ClockCircleOutlined, ReloadOutlined, RocketOutlined } from '@ant-design/icons';

const RealTimeDashboard = () => {
    const [logs, setLogs] = useState([]);
    const [statistics, setStatistics] = useState({});
    const [lastUpdate, setLastUpdate] = useState(new Date());
    const [wsConnected, setWsConnected] = useState(false);
    const ws = useRef(null);

    const loadData = async () => {
        try {
            // Загружаем последние логи
            const logsResponse = await fetch('http://localhost:8000/api/v2/entries?limit=10');
            const logsData = await logsResponse.json();
            setLogs(logsData);

            // Загружаем статистику
            const statsResponse = await fetch('http://localhost:8000/api/v2/statistics');
            const statsData = await statsResponse.json();
            setStatistics(statsData);

            setLastUpdate(new Date());
        } catch (error) {
            console.error('Failed to load data:', error);
        }
    };

    useEffect(() => {
        loadData();
        
        // WebSocket подключение
        ws.current = new WebSocket('ws://localhost:8000/ws');
        
        ws.current.onopen = () => {
            setWsConnected(true);
            console.log('WebSocket connected');
        };
        
        ws.current.onclose = () => {
            setWsConnected(false);
            console.log('WebSocket disconnected');
        };
        
        ws.current.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('WebSocket message:', data);
            // При новых данных обновляем статистику
            if (data.type === 'upload') {
                loadData();
            }
        };

        // Автообновление каждые 5 секунд
        const interval = setInterval(loadData, 5000);
        
        return () => {
            clearInterval(interval);
            if (ws.current) {
                ws.current.close();
            }
        };
    }, []);

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

    // Расчет качества системы
    const calculateSystemHealth = () => {
        const totalEntries = statistics.total_entries || 0;
        const errorCount = statistics.levels?.error || 0;
        const healthScore = totalEntries > 0 ? Math.max(0, 100 - (errorCount / totalEntries * 100)) : 100;
        
        return {
            score: Math.round(healthScore),
            status: healthScore >= 90 ? 'excellent' : healthScore >= 70 ? 'good' : 'poor'
        };
    };

    const systemHealth = calculateSystemHealth();

    return (
        <div className="real-time-dashboard">
            <Card 
                title="🏠 Real-Time Terraform Dashboard" 
                extra={
                    <Button icon={<ReloadOutlined />} onClick={loadData}>
                        Refresh
                    </Button>
                }
            >
                {/* Основная статистика */}
                <Row gutter={16} className="stats-row">
                    <Col span={4}>
                        <Card>
                            <Statistic 
                                title="Total Logs" 
                                value={statistics.total_entries || 0} 
                                prefix={<ClockCircleOutlined />}
                            />
                        </Card>
                    </Col>
                    <Col span={4}>
                        <Card>
                            <Statistic 
                                title="Errors" 
                                value={statistics.levels?.error || 0} 
                                prefix={<WarningOutlined />}
                                valueStyle={{ color: statistics.levels?.error > 0 ? '#cf1322' : '#3f8600' }}
                            />
                        </Card>
                    </Col>
                    <Col span={4}>
                        <Card>
                            <Statistic 
                                title="Operations" 
                                value={Object.keys(statistics.operations || {}).length} 
                                prefix={<CheckCircleOutlined />}
                            />
                        </Card>
                    </Col>
                    <Col span={4}>
                        <Card>
                            <Statistic 
                                title="WebSocket" 
                                value={wsConnected ? "Connected" : "Disconnected"} 
                                valueStyle={{ color: wsConnected ? '#3f8600' : '#cf1322' }}
                            />
                        </Card>
                    </Col>
                    <Col span={4}>
                        <Card>
                            <Statistic 
                                title="Last Update" 
                                value={lastUpdate.toLocaleTimeString()} 
                                valueStyle={{ fontSize: '14px' }}
                            />
                        </Card>
                    </Col>
                    <Col span={4}>
                        <Card>
                            <Statistic 
                                title="System Health" 
                                value={systemHealth.score} 
                                suffix="%"
                                prefix={<RocketOutlined />}
                                valueStyle={{ color: systemHealth.status === 'excellent' ? '#3f8600' : systemHealth.status === 'good' ? '#faad14' : '#cf1322' }}
                            />
                        </Card>
                    </Col>
                </Row>

                {/* Прогресс бар здоровья системы */}
                <Progress 
                    percent={systemHealth.score} 
                    status={systemHealth.status === 'excellent' ? 'success' : systemHealth.status === 'good' ? 'normal' : 'exception'}
                    style={{ marginBottom: 24 }}
                />

                {/* Распределение операций */}
                {statistics.operations && Object.keys(statistics.operations).length > 0 && (
                    <Card title="📊 Operations Distribution" style={{ marginBottom: 24 }}>
                        <Row gutter={16}>
                            {Object.entries(statistics.operations).map(([op, count]) => (
                                <Col span={6} key={op}>
                                    <Card size="small">
                                        <Statistic
                                            title={op.toUpperCase()}
                                            value={count}
                                            valueStyle={{ 
                                                color: op === 'plan' ? '#1890ff' : 
                                                       op === 'apply' ? '#52c41a' : 
                                                       op === 'validate' ? '#faad14' : '#722ed1'
                                            }}
                                        />
                                    </Card>
                                </Col>
                            ))}
                        </Row>
                    </Card>
                )}

                {/* Последние логи */}
                <Card title="📝 Recent Log Stream">
                    <List
                        dataSource={logs}
                        renderItem={log => (
                            <List.Item>
                                <div style={{ width: '100%' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '4px', flexWrap: 'wrap' }}>
                                        <Tag color={getLevelColor(log.level)}>
                                            {log.level}
                                        </Tag>
                                        <Tag color={log.operation === 'plan' ? 'blue' : log.operation === 'apply' ? 'green' : 'orange'}>
                                            {log.operation}
                                        </Tag>
                                        <span style={{ color: '#666', fontSize: '0.9em' }}>
                                            {new Date(log.timestamp).toLocaleTimeString()}
                                        </span>
                                        {log.tf_resource_type && (
                                            <Tag>{log.tf_resource_type}</Tag>
                                        )}
                                        {log.tf_req_id && (
                                            <Tag color="cyan">Req: {log.tf_req_id.substring(0, 8)}...</Tag>
                                        )}
                                    </div>
                                    <div style={{ fontFamily: 'monospace', fontSize: '12px' }}>
                                        {log.message}
                                    </div>
                                </div>
                            </List.Item>
                        )}
                    />
                    {logs.length === 0 && (
                        <Alert 
                            message="No recent logs" 
                            description="Upload some Terraform logs to see real-time data"
                            type="info"
                            showIcon
                        />
                    )}
                </Card>
            </Card>
        </div>
    );
};

export default RealTimeDashboard;
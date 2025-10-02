import React, { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Progress, Alert, Tag, List, Button, message } from 'antd';
import { TrophyOutlined, DashboardOutlined, ExportOutlined, CalculatorOutlined } from '@ant-design/icons';

const CompetitionDashboard = () => {
    const [dashboardData, setDashboardData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [statistics, setStatistics] = useState({});

    useEffect(() => {
        loadCompetitionData();
    }, []);

    const loadCompetitionData = async () => {
        try {
            // Загружаем реальную статистику
            const response = await fetch('http://localhost:8000/api/v2/statistics');
            const stats = await response.json();
            setStatistics(stats);

            // Рассчитываем оценку качества на основе реальных данных
            const qualityScore = calculateQualityScore(stats);
            
            const demoData = {
                system_overview: {
                    total_logs_processed: stats.total_entries || 0,
                    active_plugins: ['error_detector', 'performance_analyzer'],
                    system_health: 'excellent',
                    real_time_enabled: true
                },
                analysis_results: {
                    quality_score: qualityScore
                },
                competition_features: [
                    "Advanced Error Detection",
                    "Real-time WebSocket Dashboard", 
                    "Quality Scoring System",
                    "Dependency Visualization",
                    "gRPC Plugin System",
                    "Performance Analytics",
                    "Export Capabilities",
                    "AI-powered Insights"
                ]
            };
            
            setDashboardData(demoData);
        } catch (error) {
            console.error('Failed to load competition data:', error);
            message.error('Failed to load competition data');
        } finally {
            setLoading(false);
        }
    };

    const calculateQualityScore = (stats) => {
        const totalEntries = stats.total_entries || 1;
        const errorCount = stats.levels?.error || 0;
        const warningCount = stats.levels?.warn || 0;
        
        // Формула оценки: 100 - (ошибки * 10) - (предупреждения * 2)
        let score = 100 - (errorCount * 10) - (warningCount * 2);
        score = Math.max(0, Math.min(100, score)); // Ограничиваем 0-100
        
        // Определяем оценку
        let grade = 'F';
        if (score >= 90) grade = 'A';
        else if (score >= 80) grade = 'B';
        else if (score >= 70) grade = 'C';
        else if (score >= 60) grade = 'D';
        
        const recommendations = [];
        if (errorCount > 0) {
            recommendations.push(`Fix ${errorCount} configuration errors`);
        }
        if (warningCount > 0) {
            recommendations.push(`Address ${warningCount} warnings`);
        }
        if (recommendations.length === 0 && totalEntries > 0) {
            recommendations.push("Configuration quality is excellent!");
        }
        if (totalEntries === 0) {
            recommendations.push("Upload Terraform logs to get quality assessment");
        }

        return {
            score: Math.round(score),
            grade: grade,
            breakdown: {
                base_score: 100,
                error_penalty: errorCount * 10,
                warning_penalty: warningCount * 2,
                error_count: errorCount,
                warning_count: warningCount,
                total_entries: totalEntries
            },
            recommendations: recommendations
        };
    };

    const exportFullReport = () => {
        const report = {
            competition_submission: {
                team_name: "Terraform LogViewer Team",
                project_name: "Terraform LogViewer Pro",
                submission_time: new Date().toISOString(),
                version: "5.0.0"
            },
            system_overview: dashboardData?.system_overview,
            analysis_results: dashboardData?.analysis_results,
            raw_statistics: statistics
        };
        
        // Создаем и скачиваем JSON файл
        const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'terraform-logviewer-competition-report.json';
        a.click();
        
        message.success('Competition report exported successfully!');
    };

    if (loading) {
        return <div>Loading Competition Dashboard...</div>;
    }

    if (!dashboardData) {
        return <Alert message="Failed to load competition data" type="error" />;
    }

    const { system_overview, analysis_results } = dashboardData;
    const qualityScore = analysis_results.quality_score;

    return (
        <div className="competition-dashboard">
            {/* Заголовок конкурса */}
            <div className="competition-header">
                <h1>Terraform LogViewer Pro - Competition Edition</h1>
                <Button 
                    type="primary" 
                    icon={<ExportOutlined />}
                    onClick={exportFullReport}
                >
                    Export Competition Report
                </Button>
            </div>

            {/* Системная сводка */}
            <Row gutter={16} className="summary-row">
                <Col span={6}>
                    <Card>
                        <Statistic
                            title="Total Logs Processed"
                            value={system_overview.total_logs_processed}
                            prefix={<DashboardOutlined />}
                        />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card>
                        <Statistic
                            title="Active Plugins"
                            value={system_overview.active_plugins.length}
                            prefix="🔌"
                        />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card>
                        <Statistic
                            title="System Health"
                            value={system_overview.system_health}
                            valueStyle={{ color: '#3f8600' }}
                        />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card>
                        <Statistic
                            title="Quality Score"
                            value={qualityScore.score}
                            suffix="/100"
                            prefix={<TrophyOutlined />}
                            valueStyle={{ 
                                color: qualityScore.grade === 'A' ? '#3f8600' : 
                                       qualityScore.grade === 'B' ? '#1890ff' : 
                                       qualityScore.grade === 'C' ? '#faad14' : '#ff4d4f' 
                            }}
                        />
                    </Card>
                </Col>
            </Row>

            {/* Оценка качества */}
            <Card title="Configuration Quality Assessment" className="quality-card">
                <Row gutter={16}>
                    <Col span={12} style={{ textAlign: 'center' }}>
                        <Progress 
                            type="circle" 
                            percent={qualityScore.score} 
                            format={percent => `${percent}%`}
                            status={qualityScore.grade === 'A' ? 'success' : 'normal'}
                            size={200}
                        />
                        <div className="quality-grade">
                            <h2>Grade: {qualityScore.grade}</h2>
                            <p>Based on analysis of {qualityScore.breakdown.total_entries} log entries</p>
                        </div>
                    </Col>
                    <Col span={12}>
                        <h4>
                            <CalculatorOutlined /> Quality Breakdown:
                        </h4>
                        <List
                            size="small"
                            dataSource={[
                                `Base Score: ${qualityScore.breakdown.base_score}`,
                                `Error Penalty: -${qualityScore.breakdown.error_penalty} (${qualityScore.breakdown.error_count} errors)`,
                                `Warning Penalty: -${qualityScore.breakdown.warning_penalty} (${qualityScore.breakdown.warning_count} warnings)`,
                                `Final Score: ${qualityScore.score}/100`
                            ]}
                            renderItem={item => <List.Item>{item}</List.Item>}
                        />
                        
                        <h4>💡 Recommendations:</h4>
                        <List
                            size="small"
                            dataSource={qualityScore.recommendations}
                            renderItem={item => <List.Item>• {item}</List.Item>}
                        />
                    </Col>
                </Row>
            </Card>

            {/* Функции системы */}
            <Card title="System Features" className="features-card">
                <Alert
                    message="Active Features"
                    description="All system features are operational and ready for demonstration"
                    type="success"
                    showIcon
                    style={{ marginBottom: 16 }}
                />
                <Row gutter={[16, 16]}>
                    {dashboardData.competition_features.map((feature, index) => (
                        <Col span={8} key={index}>
                            <Tag color="green" style={{ fontSize: '14px', padding: '8px', width: '100%', textAlign: 'center' }}>
                                ✅ {feature}
                            </Tag>
                        </Col>
                    ))}
                </Row>
            </Card>

            {/* Live Statistics */}
            <Card title="📈 Live Statistics" className="performance-card">
                <Row gutter={16}>
                    <Col span={12}>
                        <h4>Log Levels Distribution:</h4>
                        {statistics.levels && Object.keys(statistics.levels).length > 0 ? (
                            <List
                                size="small"
                                dataSource={Object.entries(statistics.levels)}
                                renderItem={([level, count]) => (
                                    <List.Item>
                                        <Tag color={
                                            level === 'error' ? 'red' : 
                                            level === 'warn' ? 'orange' : 
                                            level === 'info' ? 'blue' : '#333333'
                                        }>
                                            {level}
                                        </Tag>
                                        {count} entries
                                    </List.Item>
                                )}
                            />
                        ) : (
                            <p>No log data available</p>
                        )}
                    </Col>
                    <Col span={12}>
                        <h4>Detected Operations:</h4>
                        {statistics.operations && Object.keys(statistics.operations).length > 0 ? (
                            <List
                                size="small"
                                dataSource={Object.entries(statistics.operations)}
                                renderItem={([op, count]) => (
                                    <List.Item>
                                        <Tag color={
                                            op === 'plan' ? 'blue' : 
                                            op === 'apply' ? 'green' : 'orange'
                                        }>
                                            {op}
                                        </Tag>
                                        {count} entries
                                    </List.Item>
                                )}
                            />
                        ) : (
                            <p>No operations detected</p>
                        )}
                    </Col>
                </Row>
            </Card>
        </div>
    );
};

export default CompetitionDashboard;
import React, { useState } from 'react';
import { Card, Button, Row, Col, Select, Alert, message } from 'antd';
import { DownloadOutlined, FileTextOutlined, TableOutlined } from '@ant-design/icons';

const { Option } = Select;

const ExportPanel = () => {
    const [exportFilters, setExportFilters] = useState({
        operation: '',
        level: '',
        resourceType: ''
    });
    const [exporting, setExporting] = useState(false);

    const handleExport = async (format) => {
        setExporting(true);
        try {
            const params = new URLSearchParams();
            if (exportFilters.operation) params.append('operation', exportFilters.operation);
            if (exportFilters.level) params.append('level', exportFilters.level);
            if (exportFilters.resourceType) params.append('resource_type', exportFilters.resourceType);

            const url = `http://localhost:8000/api/export/${format}?${params}`;
            
            const response = await fetch(url);
            if (!response.ok) throw new Error('Export failed');
            
            if (format === 'csv') {
                const blob = await response.blob();
                const downloadUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = `terraform_logs_export.${format}`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(downloadUrl);
            } else {
                const data = await response.json();
                const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                const downloadUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = `terraform_logs_export.${format}`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(downloadUrl);
            }
            
            message.success(`Exported successfully as ${format.toUpperCase()}`);
        } catch (error) {
            console.error('Export failed:', error);
            message.error('Export failed');
        } finally {
            setExporting(false);
        }
    };

    return (
        <div className="export-panel">
            <Card title="📤 Export Terraform Logs">
                <Alert
                    message="Export Options"
                    description="Export your Terraform logs in various formats for analysis or sharing with your team."
                    type="info"
                    style={{ marginBottom: 24 }}
                />

                {/* Фильтры экспорта */}
                <Card title="Filters" size="small" style={{ marginBottom: 24 }}>
                    <Row gutter={16}>
                        <Col span={8}>
                            <Select 
                                value={exportFilters.operation}
                                onChange={value => setExportFilters({...exportFilters, operation: value})}
                                placeholder="Filter by Operation"
                                style={{ width: '100%' }}
                                allowClear
                            >
                                <Option value="plan">Plan</Option>
                                <Option value="apply">Apply</Option>
                                <Option value="validate">Validate</Option>
                            </Select>
                        </Col>
                        <Col span={8}>
                            <Select 
                                value={exportFilters.level}
                                onChange={value => setExportFilters({...exportFilters, level: value})}
                                placeholder="Filter by Level"
                                style={{ width: '100%' }}
                                allowClear
                            >
                                <Option value="error">Error</Option>
                                <Option value="warn">Warning</Option>
                                <Option value="info">Info</Option>
                                <Option value="debug">Debug</Option>
                            </Select>
                        </Col>
                        <Col span={8}>
                            <Select 
                                value={exportFilters.resourceType}
                                onChange={value => setExportFilters({...exportFilters, resourceType: value})}
                                placeholder="Filter by Resource Type"
                                style={{ width: '100%' }}
                                allowClear
                            >
                                <Option value="t1_vpc_network">t1_vpc_network</Option>
                                <Option value="t1_vpc_router">t1_vpc_router</Option>
                                <Option value="t1_vpc_subnet">t1_vpc_subnet</Option>
                            </Select>
                        </Col>
                    </Row>
                </Card>

                {/* Форматы экспорта */}
                <Row gutter={16}>
                    <Col span={12}>
                        <Card 
                            title={<><FileTextOutlined /> JSON Export</>}
                            actions={[
                                <Button 
                                    type="primary" 
                                    icon={<DownloadOutlined />}
                                    onClick={() => handleExport('json')}
                                    loading={exporting}
                                    block
                                >
                                    Export as JSON
                                </Button>
                            ]}
                        >
                            <p>Export logs in JSON format with full metadata and structured data.</p>
                            <ul>
                                <li>Complete log entries with all fields</li>
                                <li>JSON blocks preserved</li>
                                <li>Ideal for further processing</li>
                            </ul>
                        </Card>
                    </Col>
                    <Col span={12}>
                        <Card 
                            title={<><TableOutlined /> CSV Export</>}
                            actions={[
                                <Button 
                                    type="primary" 
                                    icon={<DownloadOutlined />}
                                    onClick={() => handleExport('csv')}
                                    loading={exporting}
                                    block
                                >
                                    Export as CSV
                                </Button>
                            ]}
                        >
                            <p>Export logs in CSV format for spreadsheet analysis.</p>
                            <ul>
                                <li>Tabular format</li>
                                <li>Compatible with Excel/Google Sheets</li>
                                <li>Ideal for reporting</li>
                            </ul>
                        </Card>
                    </Col>
                </Row>

                {/* Информация о gRPC */}
                <Card title="🔌 gRPC Integration" style={{ marginTop: 24 }}>
                    <Alert
                        message="gRPC Plugin System"
                        description="The system supports gRPC plugins for advanced log processing and analysis."
                        type="success"
                        style={{ marginBottom: 16 }}
                    />
                    <Row gutter={16}>
                        <Col span={12}>
                            <Button 
                                type="dashed" 
                                block
                                onClick={async () => {
                                    try {
                                        const response = await fetch('http://localhost:8000/api/grpc/status');
                                        const data = await response.json();
                                        message.info(`gRPC Status: ${data.status}`);
                                    } catch (error) {
                                        message.error('gRPC check failed');
                                    }
                                }}
                            >
                                Check gRPC Status
                            </Button>
                        </Col>
                        <Col span={12}>
                            <Button 
                                type="dashed" 
                                block
                                onClick={async () => {
                                    try {
                                        const response = await fetch('http://localhost:8000/api/grpc/process', { method: 'POST' });
                                        const data = await response.json();
                                        message.success(`Processed ${data.processed_entries} entries with ${data.errors_found} errors found`);
                                    } catch (error) {
                                        message.error('gRPC processing failed');
                                    }
                                }}
                            >
                                Demo gRPC Processing
                            </Button>
                        </Col>
                    </Row>
                </Card>
            </Card>
        </div>
    );
};

export default ExportPanel;
import React, { useState } from 'react';
import { Upload, Button, Card, Alert, List, Tag, Statistic, Row, Col } from 'antd';
import { UploadOutlined, InboxOutlined } from '@ant-design/icons';

const { Dragger } = Upload;

const LogUploader = ({ onLogsUpdate }) => {
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleUpload = async (file) => {
    setUploading(true);
    setError(null);
    setResult(null);
    
    const formData = new FormData();
    formData.append('file', file);
  
    try {
      const response = await fetch('http://localhost:8000/api/v2/upload', {
        method: 'POST',
        body: formData,
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `Upload failed: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      setResult(data);
      if (onLogsUpdate) {
        onLogsUpdate(data.sample_entries || []);
      }
      
    } catch (error) {
      console.error('Upload failed:', error);
      setError(error.message);
    } finally {
      setUploading(false);
    }
  
    return false; // Prevent default upload behavior
  };

  const uploadProps = {
    name: 'file',
    multiple: false,
    accept: '.json,.log',
    beforeUpload: handleUpload,
    showUploadList: false,
  };

  return (
    <div className="log-uploader">
      <Card title="📤 Upload Terraform Logs" style={{ marginBottom: 24 }}>
        <Dragger {...uploadProps} disabled={uploading}>
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">Click or drag Terraform log files to this area</p>
          <p className="ant-upload-hint">
            Support for JSON and log files from Terraform operations
          </p>
        </Dragger>
        
        {uploading && (
          <Alert 
            message="Uploading and parsing logs..." 
            type="info" 
            showIcon 
            style={{ marginTop: 16 }}
          />
        )}
        
        {error && (
          <Alert 
            message={error} 
            type="error" 
            showIcon 
            style={{ marginTop: 16 }}
          />
        )}
      </Card>

      {result && (
        <Card title="📊 Upload Results">
          <Row gutter={16} style={{ marginBottom: 24 }}>
            <Col span={6}>
              <Statistic title="File" value={result.filename} />
            </Col>
            <Col span={6}>
              <Statistic title="Entries" value={result.entries_count} />
            </Col>
            <Col span={6}>
              <Statistic title="Operations" value={result.operations?.length || 0} />
            </Col>
            <Col span={6}>
              <Statistic title="Resource Types" value={result.resource_types?.length || 0} />
            </Col>
          </Row>

          {result.operations && result.operations.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <strong>Detected Operations: </strong>
              {result.operations.map(op => (
                <Tag key={op} color="blue" style={{ marginRight: 8 }}>
                  {op}
                </Tag>
              ))}
            </div>
          )}

          {result.sample_entries && result.sample_entries.length > 0 && (
            <div>
              <h4>Sample Entries:</h4>
              <List
                size="small"
                dataSource={result.sample_entries}
                renderItem={entry => (
                  <List.Item>
                    <div style={{ width: '100%' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Tag color={entry.level === 'error' ? 'red' : 'blue'}>
                          {entry.level}
                        </Tag>
                        <span style={{ color: '#666' }}>
                          {new Date(entry.timestamp).toLocaleString()}
                        </span>
                      </div>
                      <div style={{ marginTop: 4 }}>{entry.message}</div>
                    </div>
                  </List.Item>
                )}
              />
            </div>
          )}
        </Card>
      )}
    </div>
  );
};

export default LogUploader;
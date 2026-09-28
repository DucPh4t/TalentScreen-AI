'use client';

import React, { useState, useRef, useCallback } from 'react';
import { api } from '../lib/api';
import { toast } from './Toast';

interface BatchFileItem {
  id: string;
  file: File;
  status: 'queued' | 'uploading' | 'success' | 'error';
  progress: number;
  errorMsg?: string;
  applicationId?: string;
}

interface BatchDropzoneProps {
  requisitionId: string;
  onUploadComplete: () => Promise<void> | void;
  onClose?: () => void;
}

export default function BatchDropzone({ requisitionId, onUploadComplete, onClose }: BatchDropzoneProps) {
  const [fileQueue, setFileQueue] = useState<BatchFileItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [totalProgress, setTotalProgress] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((incomingFiles: FileList | File[]) => {
    const validExtensions = ['.pdf', '.docx', '.txt'];
    const newItems: BatchFileItem[] = [];

    Array.from(incomingFiles).forEach((file) => {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!validExtensions.includes(ext)) {
        toast.warning(`Tệp "${file.name}" không hợp lệ. Chỉ chấp nhận .pdf, .docx, .txt.`);
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        toast.error(`Tệp "${file.name}" vượt quá giới hạn 10MB.`);
        return;
      }

      // Check if already in queue
      const exists = fileQueue.some((item) => item.file.name === file.name && item.file.size === file.size);
      if (!exists) {
        newItems.push({
          id: 'bf_' + Math.random().toString(36).substring(2, 9),
          file,
          status: 'queued',
          progress: 0
        });
      }
    });

    if (newItems.length > 0) {
      setFileQueue((prev) => [...prev, ...newItems]);
      toast.info(`Đã thêm ${newItems.length} tệp vào hàng đợi tiếp nhận hồ sơ.`);
    }
  }, [fileQueue]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(e.target.files);
    }
    // reset input so the same file can be re-selected if removed
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeFile = (id: string) => {
    if (isUploading) return;
    setFileQueue((prev) => prev.filter((item) => item.id !== id));
  };

  const clearQueue = () => {
    if (isUploading) return;
    setFileQueue([]);
  };

  const startBatchUpload = async () => {
    const pendingItems = fileQueue.filter((item) => item.status === 'queued' || item.status === 'error');
    if (pendingItems.length === 0) {
      toast.info('Không có tệp nào đang chờ tải lên.');
      return;
    }

    setIsUploading(true);
    let completedCount = 0;
    const totalCount = pendingItems.length;

    for (const item of pendingItems) {
      // Update item to uploading
      setFileQueue((prev) =>
        prev.map((f) => (f.id === item.id ? { ...f, status: 'uploading', progress: 20 } : f))
      );

      try {
        // Step 1: Create application
        const createdApp = await api.createApplication(requisitionId);
        setFileQueue((prev) =>
          prev.map((f) => (f.id === item.id ? { ...f, applicationId: createdApp.id, progress: 50 } : f))
        );

        // Step 2: Upload document
        await api.uploadDocument(createdApp.id, item.file);

        // Step 3: Complete
        completedCount++;
        setFileQueue((prev) =>
          prev.map((f) => (f.id === item.id ? { ...f, status: 'success', progress: 100 } : f))
        );
      } catch (err: any) {
        setFileQueue((prev) =>
          prev.map((f) =>
            f.id === item.id
              ? { ...f, status: 'error', progress: 0, errorMsg: err.message || 'Lỗi tải lên' }
              : f
          )
        );
      }

      setTotalProgress(Math.round((completedCount / totalCount) * 100));
    }

    setIsUploading(false);
    toast.success(`Đã xử lý xong hàng loạt! Thành công: ${completedCount}/${totalCount} hồ sơ.`);
    await onUploadComplete();
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', width: '100%' }}>
      {/* Dropzone Area */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Khu vực kéo thả nhiều tệp CV"
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && !isUploading) {
            e.preventDefault();
            fileInputRef.current?.click();
          }
        }}
        style={{
          border: isDragging ? '2px dashed #0d9488' : '2px dashed rgba(24, 24, 27, 0.2)',
          borderRadius: '1.25rem',
          padding: '2.5rem 1.5rem',
          textAlign: 'center',
          backgroundColor: isDragging ? 'rgba(13, 148, 136, 0.08)' : 'rgba(255, 255, 255, 0.7)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          cursor: isUploading ? 'not-allowed' : 'pointer',
          transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '0.75rem'
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.txt"
          onChange={handleFileInputChange}
          style={{ display: 'none' }}
        />

        <div
          style={{
            width: '56px',
            height: '56px',
            borderRadius: '16px',
            backgroundColor: isDragging ? '#0d9488' : 'rgba(13, 148, 136, 0.12)',
            color: isDragging ? '#ffffff' : '#0d9488',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'all 0.2s ease',
            boxShadow: isDragging ? '0 10px 25px -5px rgba(13, 148, 136, 0.4)' : 'none'
          }}
        >
          <span className="material-symbols-outlined" style={{ fontSize: '28px' }}>
            upload_file
          </span>
        </div>

        <div>
          <h4 style={{ fontSize: '15px', fontWeight: 700, color: '#111827', marginBottom: '0.25rem' }}>
            {isDragging ? 'Thả các tệp CV vào đây ngay' : 'Kéo & Thả Hàng Loạt File CV (PDF, DOCX, TXT)'}
          </h4>
          <p style={{ fontSize: '12.5px', color: '#4b5563' }}>
            Hỗ trợ kéo thả đồng thời 10–50 file. Dung lượng tối đa 10 MB/tệp.
          </p>
        </div>

        <button
          type="button"
          disabled={isUploading}
          style={{
            marginTop: '0.5rem',
            padding: '0.5rem 1.25rem',
            borderRadius: '0.75rem',
            background: '#ffffff',
            border: '1px solid rgba(24, 24, 27, 0.15)',
            fontSize: '12px',
            fontWeight: 600,
            color: '#111827',
            cursor: isUploading ? 'not-allowed' : 'pointer',
            boxShadow: '0 2px 6px rgba(0,0,0,0.04)'
          }}
        >
          Hoặc chọn tệp từ máy tính
        </button>
      </div>

      {/* Queue Summary & Control Bar */}
      {fileQueue.length > 0 && (
        <div
          style={{
            background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.96) 0%, rgba(255, 253, 250, 0.92) 100%)',
            borderRadius: '1rem',
            padding: '1.25rem',
            border: '1px solid rgba(24, 24, 27, 0.1)',
            boxShadow: '0 8px 24px -4px rgba(24, 24, 27, 0.06)'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div>
              <strong style={{ fontSize: '14px', color: '#111827' }}>
                Hàng Đợi Tiếp Nhận ({fileQueue.length} hồ sơ)
              </strong>
              <span style={{ fontSize: '12px', color: '#4b5563', marginLeft: '0.5rem' }}>
                (Tổng dung lượng: {formatFileSize(fileQueue.reduce((acc, f) => acc + f.file.size, 0))})
              </span>
            </div>

            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                type="button"
                onClick={clearQueue}
                disabled={isUploading}
                style={{
                  padding: '0.45rem 0.85rem',
                  borderRadius: '8px',
                  border: '1px solid rgba(24, 24, 27, 0.12)',
                  background: '#ffffff',
                  fontSize: '12px',
                  color: '#52525b',
                  cursor: isUploading ? 'not-allowed' : 'pointer'
                }}
              >
                Xóa tất cả
              </button>
              <button
                type="button"
                onClick={startBatchUpload}
                disabled={isUploading || fileQueue.every((f) => f.status === 'success')}
                className="btn btn-primary"
                style={{ padding: '0.45rem 1.25rem', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
              >
                {isUploading ? (
                  <>
                    <span className="material-symbols-outlined" style={{ fontSize: '15px', animation: 'spin 1s linear infinite' }}>
                      autorenew
                    </span>
                    <span>Đang tải lên ({totalProgress}%)…</span>
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined" style={{ fontSize: '15px' }}>
                      cloud_upload
                    </span>
                    <span>Tiếp nhận toàn bộ ({fileQueue.filter((f) => f.status !== 'success').length})</span>
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Overall Batch Progress */}
          {isUploading && (
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#4b5563', marginBottom: '4px' }}>
                <span>Tiến trình xử lý hàng loạt</span>
                <span>{totalProgress}%</span>
              </div>
              <div style={{ height: '6px', background: 'rgba(24, 24, 27, 0.08)', borderRadius: '9999px', overflow: 'hidden' }}>
                <div
                  style={{
                    height: '100%',
                    width: `${totalProgress}%`,
                    background: 'linear-gradient(90deg, #0d9488 0%, #14b8a6 100%)',
                    transition: 'width 0.3s ease'
                  }}
                />
              </div>
            </div>
          )}

          {/* Files List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '280px', overflowY: 'auto', paddingRight: '4px' }}>
            {fileQueue.map((item, idx) => (
              <div
                key={item.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.65rem 0.85rem',
                  borderRadius: '10px',
                  background: '#ffffff',
                  border: '1px solid rgba(24, 24, 27, 0.08)',
                  gap: '0.75rem'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flex: 1, minWidth: 0 }}>
                  <span style={{ fontSize: '11px', color: '#6b7280', fontFamily: 'var(--font-mono, monospace)' }}>
                    #{idx + 1}
                  </span>
                  <div
                    style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '6px',
                      backgroundColor: 'rgba(13, 148, 136, 0.1)',
                      color: '#0d9488',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '9.5px',
                      fontWeight: 700,
                      fontFamily: 'var(--font-mono, monospace)',
                      flexShrink: 0
                    }}
                  >
                    {item.file.name.split('.').pop()?.toUpperCase() || 'CV'}
                  </div>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: '12.5px', fontWeight: 600, color: '#111827', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {item.file.name}
                    </div>
                    <div style={{ fontSize: '11px', color: '#4b5563' }}>
                      {formatFileSize(item.file.size)}
                    </div>
                  </div>
                </div>

                {/* Status Indicator */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  {item.status === 'queued' && (
                    <span style={{ fontSize: '11px', color: '#52525b', background: 'rgba(24, 24, 27, 0.06)', padding: '2px 8px', borderRadius: '9999px', fontWeight: 500 }}>
                      Chờ tải
                    </span>
                  )}
                  {item.status === 'uploading' && (
                    <span style={{ fontSize: '11px', color: '#0d9488', background: 'rgba(13, 148, 136, 0.1)', padding: '2px 8px', borderRadius: '9999px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span className="material-symbols-outlined" style={{ fontSize: '12px', animation: 'spin 1s linear infinite' }}>
                        progress_activity
                      </span>
                      Đang xử lý &amp; che PII…
                    </span>
                  )}
                  {item.status === 'success' && (
                    <span style={{ fontSize: '11px', color: '#047857', background: 'rgba(16, 185, 129, 0.12)', padding: '2px 8px', borderRadius: '9999px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span className="material-symbols-outlined" style={{ fontSize: '13px' }}>check_circle</span>
                      Hoàn thành
                    </span>
                  )}
                  {item.status === 'error' && (
                    <span style={{ fontSize: '11px', color: '#be123c', background: 'rgba(244, 63, 94, 0.12)', padding: '2px 8px', borderRadius: '9999px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span className="material-symbols-outlined" style={{ fontSize: '13px' }}>error</span>
                      {item.errorMsg || 'Lỗi'}
                    </span>
                  )}

                  {!isUploading && item.status !== 'success' && (
                    <button
                      type="button"
                      onClick={() => removeFile(item.id)}
                      aria-label="Xóa tệp khỏi hàng đợi"
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: '#71717a',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        padding: '2px'
                      }}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: '16px' }}>close</span>
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

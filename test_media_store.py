import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import media_store
import karaoke_web as web
import studio_store


class MediaStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'media.mp4'
        self.path.write_bytes(b'original media')
        self.sdk = MagicMock()
        self.sdk.put_blob.return_value = SimpleNamespace(url='https://store.private.blob.vercel-storage.com/media.mp4')
        self.environment = patch.dict(os.environ, {'BLOB_READ_WRITE_TOKEN': 'test-token', 'DATABASE_URL': ''})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.modules = patch.dict('sys.modules', {'vercel.blob.sync': self.sdk})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        studio_store._MEDIA_BLOBS.clear()

    def test_local_mode_needs_no_sdk_or_storage(self):
        os.environ.pop('BLOB_READ_WRITE_TOKEN')
        self.assertIsNone(media_store.put_file('video/key', self.path, 'video/mp4'))
        self.assertFalse(media_store.restore_file('unused', self.path))
        self.sdk.put_blob.assert_not_called()

    def test_upload_is_private_and_streamed(self):
        def consume(key, body, **options):
            self.assertEqual(body.read(8), b'original')
            self.assertEqual(options['content_length'], self.path.stat().st_size)
            self.assertEqual(options['access'], 'private')
            return SimpleNamespace(url='saved-url')
        self.sdk.put_blob.side_effect = consume
        self.assertEqual(media_store.put_file('video/key', self.path, 'video/mp4'), 'saved-url')

    def test_upload_failure_is_not_silent_and_does_not_expose_secrets(self):
        self.sdk.put_blob.side_effect = RuntimeError('test-token private diagnostic')
        with self.assertRaises(media_store.BlobUploadError) as error:
            media_store.put_file('video/key', self.path, 'video/mp4')
        self.assertNotIn('test-token', str(error.exception))

    def test_restore_streams_private_file_and_replaces_atomically(self):
        self.sdk.stream_blob.return_value.__enter__.return_value = iter([b'restored ', b'media'])
        self.assertTrue(media_store.restore_file('saved-url', self.path))
        self.assertEqual(self.path.read_bytes(), b'restored media')
        self.sdk.stream_blob.assert_called_once_with('saved-url', access='private')
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_failed_restore_keeps_old_file_and_cleans_partial_download(self):
        def interrupted():
            yield b'partial'
            raise IOError('network interrupted')
        self.sdk.stream_blob.return_value.__enter__.return_value = interrupted()
        self.assertFalse(media_store.restore_file('saved-url', self.path))
        self.assertEqual(self.path.read_bytes(), b'original media')
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_audio_retry_with_existing_file_cannot_skip_failed_upload(self):
        with patch.object(web.engine, 'audio_cache_path', return_value=str(self.path)), \
             patch.object(web.engine, 'download_audio_track', return_value=str(self.path)):
            self.sdk.put_blob.side_effect = IOError('quota')
            with self.assertRaises(media_store.BlobUploadError):
                web._ensure_audio_local('audit', 'song')
            self.assertEqual(studio_store._MEDIA_BLOBS, {})
            self.sdk.put_blob.side_effect = None
            self.assertEqual(web._ensure_audio_local('audit', 'song'), self.path)
            self.assertEqual(self.sdk.put_blob.call_count, 2)
            self.assertTrue(studio_store._MEDIA_BLOBS)

    def test_busy_studio_rejects_extra_job_without_running_it(self):
        with web._STUDIO_JOB, patch.object(web, '_prepare_studio_payload') as prepare:
            response = web.app.test_client().post('/api/v1/studio-sessions', json={})
        self.assertEqual(response.status_code, 503)
        prepare.assert_not_called()
        self.assertFalse(web._STUDIO_JOB.locked())


if __name__ == '__main__':
    unittest.main()

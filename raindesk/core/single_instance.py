"""raindesk/core/single_instance.py

الغرض: منع تشغيل أكثر من نسخة، وتنبيه النسخة الأولى عند محاولة تشغيل ثانية.
المسؤوليات: خادم QLocalServer (named pipe في Windows) في النسخة الأولى، وعميل يرسل الرسالة
    'show_settings' من النسخة الثانية قبل أن تخرج.
الاعتماديات: QtCore وQtNetwork فقط.
النمط التصميمي: Singleton على مستوى العملية عبر IPC (Inter-Process Communication).
ملاحظات أمنية: الخادم يقبل اتصالات المستخدم نفسه فقط (UserAccessOption)، ويقرأ حتى 64 بايت
    ولا ينفّذ إلا رسالة معروفة واحدة؛ أي محتوى آخر يُتجاهل.
مثال: guard = SingleInstanceGuard(); primary = guard.acquire()
"""

from __future__ import annotations

import logging
from functools import partial
from typing import Final

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from raindesk.core.constants import IPC_SERVER_NAME

_LOG = logging.getLogger(__name__)

_MSG_SHOW_SETTINGS: Final[bytes] = b"show_settings"  # الرسالة الوحيدة المفهومة
_MAX_MESSAGE_BYTES: Final[int] = 64  # سقف ما نقرؤه من أي عميل (حماية من بيانات ضخمة)
_CONNECT_TIMEOUT_MS: Final[int] = 1000  # ms: مهلة الاتصال والكتابة عند مراسلة النسخة الأولى


class SingleInstanceGuard(QObject):
    """حارس النسخة الواحدة؛ يُنشأ بعد QApplication ويبقى حيًّا حتى إغلاق التطبيق."""

    activation_requested = Signal()  # نسخة ثانية طلبت إظهار نافذة الإعدادات

    def __init__(self, name: str = IPC_SERVER_NAME, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._name = name
        self._server: QLocalServer | None = None

    def acquire(self) -> bool:
        """يحاول أن يصير هذا المسار هو النسخة الأولى؛ True إذا نجح.

        الخوارزمية: نجرّب listen؛ إن فشل نسأل هل يوجد من يردّ على الاسم؟ نعم فهناك نسخة أخرى
        (نعيد False)، لا فالخادم قديم عالق (يحدث على أنظمة تترك ملف socket) فنزيله ونعيد المحاولة.
        إن تعذّر إنشاء الخادم لسبب غير متوقع نكمل كنسخة أولى بلا حماية بدل منع التشغيل تمامًا.
        """
        if self._server is not None:
            return True
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(self._name):
            if self._another_instance_answers():
                server.deleteLater()
                return False
            QLocalServer.removeServer(self._name)
            if not server.listen(self._name):
                _LOG.warning("single-instance server failed: %s", server.errorString())
                server.deleteLater()
                return True  # نفضّل نسخة بلا حماية على تطبيق لا يعمل
        server.newConnection.connect(self._on_new_connection)
        self._server = server
        return True

    def _another_instance_answers(self) -> bool:
        """يتصل بالاسم كعميل تجريبي؛ True إذا ردّ أحد (أي توجد نسخة حيّة)."""
        probe = QLocalSocket(self)
        probe.connectToServer(self._name)
        connected = probe.waitForConnected(_CONNECT_TIMEOUT_MS)
        probe.abort()
        probe.deleteLater()
        return connected

    def _on_new_connection(self) -> None:
        """يستقبل الاتصالات الواردة؛ كل اتصال يُقرأ مرة واحدة ثم يُغلق."""
        server = self._server
        if server is None:
            return
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            if socket is None:
                break
            socket.disconnected.connect(socket.deleteLater)
            socket.readyRead.connect(partial(self._on_ready_read, socket))
            if socket.bytesAvailable() > 0:  # البيانات وصلت قبل ربط readyRead
                self._on_ready_read(socket)

    def _on_ready_read(self, socket: QLocalSocket) -> None:
        data = bytes(socket.read(_MAX_MESSAGE_BYTES)).strip()
        if data == _MSG_SHOW_SETTINGS:
            self.activation_requested.emit()
        else:
            _LOG.debug("ignoring unknown IPC message (%d bytes)", len(data))
        socket.disconnectFromServer()

    def notify_primary(self) -> bool:
        """يرسل 'show_settings' إلى النسخة الأولى؛ True إذا كُتبت الرسالة بنجاح.

        يحجب حتى ثانيتين على الأكثر، وهذا مقبول لأنه يُستدعى من النسخة الثانية فقط قبل خروجها.
        """
        socket = QLocalSocket(self)
        socket.connectToServer(self._name)
        if not socket.waitForConnected(_CONNECT_TIMEOUT_MS):
            _LOG.warning("cannot reach the primary instance: %s", socket.errorString())
            socket.deleteLater()
            return False
        socket.write(_MSG_SHOW_SETTINGS)
        sent = socket.waitForBytesWritten(_CONNECT_TIMEOUT_MS)
        socket.disconnectFromServer()
        if socket.state() != QLocalSocket.LocalSocketState.UnconnectedState:
            socket.waitForDisconnected(_CONNECT_TIMEOUT_MS)
        socket.deleteLater()
        return sent

    def shutdown(self) -> None:
        """يغلق الخادم ويحرّر الاسم؛ آمن عند الاستدعاء أكثر من مرة."""
        server, self._server = self._server, None
        if server is not None:
            server.close()
            QLocalServer.removeServer(self._name)
            server.deleteLater()
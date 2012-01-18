#include "TcpEdge.hpp"
#include "Utils/Serialization.hpp"

using Dissent::Utils::Serialization;

namespace Dissent {
namespace Transports {
  const QByteArray TcpEdge::Zero = QByteArray(4, 0);

  TcpEdge::TcpEdge(const Address &local, const Address &remote, bool outgoing,
      QTcpSocket *socket) :
    Edge(local, remote, outgoing),
    _socket(socket, &QObject::deleteLater)
  {
    socket->setParent(0);

    QObject::connect(socket, SIGNAL(readyRead()), this, SLOT(Read()));
    QObject::connect(socket, SIGNAL(disconnected()), this, SLOT(HandleDisconnect()));
  }

  TcpEdge::~TcpEdge()
  {
  }

  void TcpEdge::Send(const QByteArray &data)
  {
    if(_closed) {
      qWarning() << "Attempted to send on a closed edge.";
      return;
    }

    QByteArray length(4, 0);
    Serialization::WriteInt(data.size(), length, 0);
    if((_socket->write(length) != 4) ||
        (_socket->write(data) != data.size()) ||
        (_socket->write(Zero) != 4))
    {
      qCritical() << "Didn't write all data to the socket!!!!!";
    }

    qDebug() << "Just sent" << data.size() << "byte message via" << ToString();
  }

  void TcpEdge::Read()
  {
    int total_length = _socket->bytesAvailable();

    while(total_length >= 8) {
      qDebug() << "Total bytes available:" << total_length << ToString();
      QByteArray length_arr = _socket->peek(4);
      if(length_arr.isEmpty()) {
        qCritical() << "Error reading Tcp socket in" << ToString();
        Close("Error reading Tcp socket");
        return;
      }

      int length = Serialization::ReadInt(length_arr, 0);
      if(length + 8 > total_length) {
        qDebug() << "Available data not long enough!" << total_length << length << ToString();
        break;
      }

      if(length < 0) {
        Close("Error reading Tcp socket");
        return;
      }

      QByteArray msg = _socket->read(length + 8);
      if(msg.isEmpty()) {
        Close("Error reading Tcp socket");
        qCritical() << "Error reading Tcp socket in" << ToString();
        return;
      }

      if(Serialization::ReadInt(msg, length + 4) != 0) {
        qCritical() << "Mismatch on byte array!";
      }

      qDebug() << "Pushing a message of size:" << length << ToString();
      PushData(msg.mid(4, length), this);
      total_length = _socket->bytesAvailable();
    }
  }

  bool TcpEdge::Close(const QString& reason)
  {
    if(!Edge::Close(reason)) {
      return false;
    }

    _socket->close();
    return true;
  }

  void TcpEdge::HandleDisconnect()
  {
    if(_closed) {
      CloseCompleted();
      return;
    }

    if(_close_reason.isEmpty()) {
      _close_reason = "Disconnected";
    }
    Edge::Close(_close_reason);
    CloseCompleted();
  }
}
}

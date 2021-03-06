#ifndef DISSENT_TESTS_MOCK_H_GUARD
#define DISSENT_TESTS_MOCK_H_GUARD

#include <QByteArray>
#include <QObject>
#include <QScopedPointer>

#include "DissentTest.hpp"

namespace Dissent {
namespace Tests {
  class MockSource : public Source {
    public:
      void IncomingData(const QByteArray &data, ISender *from);
  };

  class MockSender : public ISender {
    public:
      explicit MockSender(MockSource *source);
      virtual ~MockSender() {}
      virtual void Send(const QByteArray &data);
      void SetReturnPath(ISender *sender);
    private:
      MockSource *_source;
      ISender *_from;
  };

  class MockSink : public ISink {
    public:
      virtual ~MockSink() {}
      virtual void HandleData(const QByteArray &data, ISender *from);
      const QByteArray GetLastData();
      ISender *GetLastSender();
    private:
      ISender *_last_sender;
      QByteArray _last_data;
  };

  class MockSinkWithSignal : public QObject, public MockSink {
    Q_OBJECT

    public:
      virtual ~MockSinkWithSignal() {}
      virtual void HandleData(const QByteArray &data, ISender *from);
    signals:
      void ReadReady(MockSinkWithSignal *sink);
  };

  class MockEdgeHandler : public QObject {
    Q_OBJECT

    public:
      explicit MockEdgeHandler(EdgeListener *el);
      virtual ~MockEdgeHandler() {}
      QSharedPointer<Edge> edge;
    private slots:
      void HandleEdge(QSharedPointer<Edge> edge);
  };
  
  void MockExec();
  void MockExecLoop(SignalCounter &sc, int interval = 0);
}
}
#endif

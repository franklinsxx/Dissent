#include "Utils/Logging.hpp"

#include "Settings.hpp"

using Dissent::Utils::Logging;

namespace Dissent {
namespace Applications {
  Settings::Settings(const QString &file, bool actions) :
    LocalId(Id::Zero()),
    LeaderId(Id::Zero()),
    SubgroupPolicy(Group::CompleteGroup),
    _use_file(true),
    _settings(file, QSettings::IniFormat),
    _reason()
  {
    Init();
    QVariant peers = _settings.value("remote_peers");
    ParseUrlList("RemotePeer", peers, RemotePeers);

    QVariant endpoints = _settings.value("endpoints");
    ParseUrlList("EndPoint", endpoints, LocalEndPoints);

    DemoMode = _settings.value("demo_mode").toBool();

    if(_settings.contains("local_nodes")) {
      LocalNodeCount = _settings.value("local_nodes").toInt();
    }

    if(_settings.contains("web_server_url")) {
      QString url = _settings.value("web_server_url").toString();
      WebServerUrl = QUrl(url);
      if(WebServerUrl.toString() != url) {
        WebServerUrl = QUrl();
      }

      QString scheme = WebServerUrl.scheme();
      if(scheme != "http") {
        WebServerUrl = QUrl();
      }
    }

    if(_settings.contains("session_type")) {
      SessionType = _settings.value("session_type").toString();
    }

    if(_settings.contains("subgroup_policy")) {
      QString ptype = _settings.value("subgroup_policy").toString();
      SubgroupPolicy = Group::StringToPolicyType(ptype);
    }

    if(_settings.contains("log")) {
      Log = _settings.value("log").toString();
      QString lower = Log.toLower();

      if(actions) {
        if(lower == "stderr") {
          Logging::UseStderr();
        } else if(lower == "stdout") {
          Logging::UseStdout();
        } else if(Log.isEmpty()) {
          Logging::Disable();
        } else {
          Logging::UseFile(Log);
        }
      }
    }

    Console = _settings.value("console").toBool();
    WebServer = _settings.value("web_server").toBool();
    Multithreading = _settings.value("multithreading").toBool();

    if(_settings.contains("local_id")) {
      LocalId = Id(_settings.value("local_id").toString());
    }

    if(_settings.contains("leader_id")) {
      LeaderId = Id(_settings.value("leader_id").toString());
    }
  }

  Settings::Settings() :
    LocalId(Id::Zero()),
    LeaderId(Id::Zero()),
    SubgroupPolicy(Group::CompleteGroup),
    _use_file(false)
  {
    Init();
  }

  void Settings::Init()
  {
    LocalNodeCount = 1;
    SessionType = "null";
    Console = false;
    WebServer = false;
  }

  bool Settings::IsValid()
  {
    if(_use_file && (_settings.status() != QSettings::NoError)) {
      _reason = "File error";
      return false;
    }

    if(LocalEndPoints.count() == 0) {
      _reason = "No locally defined end points";
      return false;
    }

    if(WebServer && !WebServerUrl.isValid()) {
      _reason = "Invalid WebServerUrl";
      return false;
    }

    if(LeaderId == Id::Zero()) {
      _reason = "No leader Id";
      return false;
    }

    if(SubgroupPolicy == -1) {
      _reason = "Invlaid subgroup policy";
      return false;
    }

    return true;
  }

  QString Settings::GetError()
  {
    IsValid();
    return _reason;
  }

  void Settings::ParseUrlList(const QString &name, const QVariant &values,
          QList<QUrl> &list)
  {
    if(values.isNull()) {
      return;
    }

    QVariantList varlist = values.toList();
    if(!varlist.empty()) {
      foreach(QVariant value, varlist) {
        ParseUrl(name, value, list);
      }
    } else {
      ParseUrl(name, values, list);
    }
  }

  inline void Settings::ParseUrl(const QString &name, const QVariant &value,
          QList<QUrl> &list)
  {
    QUrl url(value.toString());
    if(url.isValid()) {
      list << url;
    } else {
      qCritical() << "Invalid " << name << ": " << value.toString();
    }
  }

  void Settings::Save()
  {
    if(!_use_file) {
      return;
    }

    QStringList peers;
    foreach(QUrl peer, RemotePeers) {
      peers << peer.toString();
    }

    if(!peers.empty()) {
      _settings.setValue("remote_peers", peers);
    }

    QStringList endpoints;
    foreach(QUrl endpoint, LocalEndPoints) {
      endpoints << endpoint.toString();
    }

    if(!endpoints.empty()) {
      _settings.setValue("endpoints", endpoints);
    }

    _settings.setValue("local_nodes", LocalNodeCount);
    _settings.setValue("web_server", WebServer);
    _settings.setValue("web_server_url", WebServerUrl);
    _settings.setValue("console", Console);
    _settings.setValue("demo_mode", DemoMode);
    _settings.setValue("log", Log);
    _settings.setValue("multithreading", Multithreading);
    _settings.setValue("local_id", LocalId.ToString());
    _settings.setValue("leader_id", LeaderId.ToString());
    _settings.setValue("subgroup_policy",
        Group::PolicyTypeToString(SubgroupPolicy));
  }
}
}

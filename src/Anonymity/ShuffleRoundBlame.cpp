#include "ShuffleRoundBlame.hpp"

#include "Crypto/CryptoFactory.hpp"
#include "Connections/EmptyNetwork.hpp"

using Dissent::Crypto::CryptoFactory;
using Dissent::Crypto::Hash;
using Dissent::Crypto::Library;
using Dissent::Crypto::OnionEncryptor;

namespace Dissent {
namespace Anonymity {
  ShuffleRoundBlame::ShuffleRoundBlame(const Group &group, const Id &local_id,
      const Id &round_id, AsymmetricKey *outer_key) :
    ShuffleRound(group, Credentials(local_id, QSharedPointer<AsymmetricKey>(),
          QSharedPointer<DiffieHellman>()),
        round_id, Dissent::Connections::EmptyNetwork::GetInstance(),
        Dissent::Messaging::EmptyGetDataCallback::GetInstance())
  {
    if(outer_key) {
      Library *lib = CryptoFactory::GetInstance().GetLibrary();
      _outer_key.reset(lib->LoadPrivateKeyFromByteArray(outer_key->GetByteArray()));
    }
    _log.ToggleEnabled();
  }

  bool ShuffleRoundBlame::Start()
  {
    QScopedPointer<AsymmetricKey> tmp(_outer_key.take());
    bool nstarted = ShuffleRound::Start();
    _outer_key.reset(tmp.take());
    return !nstarted;
  }

  int ShuffleRoundBlame::GetGo(int idx)
  {
    if(_go_received[idx]) {
      return _go[idx] ? 1 : - 1;
    }
    return 0;
  }

  void ShuffleRoundBlame::BroadcastPublicKeys()
  {
    _state = KeySharing;
  }

  void ShuffleRoundBlame::SubmitData()
  {
    if(_shuffler) {
      _state = WaitingForShuffle;
    } else {
      _state = ShuffleRound::WaitingForEncryptedInnerData;
    }
  }

  void ShuffleRoundBlame::Shuffle()
  {
    _state = ShuffleRound::Shuffling;

    OnionEncryptor *oe = CryptoFactory::GetInstance().GetOnionEncryptor();
    oe->Decrypt(_outer_key.data(), _shuffle_ciphertext, _shuffle_cleartext,
        &_bad_members);

    _state = ShuffleRound::WaitingForEncryptedInnerData;
  }

  void ShuffleRoundBlame::VerifyInnerCiphertext()
  {
    Library *lib = CryptoFactory::GetInstance().GetLibrary();
    QScopedPointer<Hash> hash(lib->GetHashAlgorithm());

    for(int idx = 0; idx < _public_inner_keys.count(); idx++) {
      hash->Update(_public_inner_keys[idx]->GetByteArray());
      hash->Update(_public_outer_keys[idx]->GetByteArray());
      hash->Update(_encrypted_data[idx]);
    }
    _broadcast_hash = hash->ComputeHash();
  }

  void ShuffleRoundBlame::StartBlame()
  {
  }

  void ShuffleRoundBlame::BroadcastPrivateKey()
  {
    _state = PrivateKeySharing;
  }

  void ShuffleRoundBlame::Decrypt()
  {
  }

  void ShuffleRoundBlame::BlameRound()
  {
  }
}
}

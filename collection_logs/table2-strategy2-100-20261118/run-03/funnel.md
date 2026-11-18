# Collection funnel

Denominator: 100; integrity: FAILED; saved: 0.
| Stage | Independent | Prefix | States |
|---|---:|---:|---|
| claimed | 47 | 47 | {"reached": 47, "not_reached": 53} |
| first_frame | 27 | 27 | {"reached": 27, "failed": 20, "not_reached": 53} |
| template_selected | 26 | 26 | {"reached": 26, "not_reached": 73, "unknown": 1} |
| model_http | 0 | 0 | {"not_reached": 100} |
| initial_plan_accepted | 0 | 0 | {"unknown": 27, "not_reached": 73} |
| effective_steps_ge5 | 0 | 0 | {"unknown": 27, "not_reached": 73} |
| goal_verified | 0 | 0 | {"unknown": 27, "not_reached": 73} |
| formally_saved | 0 | 0 | {"unknown": 27, "not_reached": 73} |

Usage and per-candidate evidence are in funnel.json.

Issues: ["fixed_100_claims_incomplete", "unsettled_claims"]

Saved mean input tokens: None; amortized input tokens: None

## Complete machine facts

```json
{
  "denominator": 100,
  "expected_denominator": 100,
  "site_denominators": {
    "app-692a94fed923f056a6a862fd": 3,
    "app-e3de3e48b34ab6788b7fd88c": 3,
    "app-69ff7af2ff194f3bd06fd4f7": 3,
    "app-9edd3238c39e0ec4f8ba2a4d": 3,
    "app-7997578ee50cd7f69091be58": 3,
    "app-a14a91aa44851afdd6775189": 3,
    "app-d533e3a4791e825199bf2c30": 3,
    "app-2534307b2632cec2f235901d": 3,
    "app-7fbe8bdae7a8b2ade139044b": 3,
    "app-e8ef9bc3028112bc32053886": 2,
    "app-dbc12c0fe08fee9b0d1e2ccf": 1,
    "app-636a2f32f6f61b737150de21": 3,
    "app-95f7633955f9037494bbe989": 3,
    "app-57e27368f9fb3d90ed521bf0": 3,
    "app-f5189cfa26c0bbd0f14c08b1": 3,
    "app-e79976782188a884e4e6d6fe": 3,
    "app-fc64872577d7c22f2d8b2bd0": 3,
    "app-758780c85e102a55d26755b7": 3,
    "app-72e259702360691d76096239": 3,
    "app-3759a408b490a1eec05b8ae0": 2,
    "app-ae9c4c62f5d1362f731e3873": 2,
    "app-0ffd0c8a72d9b9db3da6ca9d": 2,
    "app-d64d6954ab4483412bfb3d4a": 2,
    "app-bc9b5b27eb3c32f1774429d6": 2,
    "app-6cd7b65ba2ab7aa4639301be": 2,
    "app-f8047ab6666258671666046f": 2,
    "app-f26113b93443c5df3770b880": 2,
    "app-e8bb513049e5b87eab79a71d": 1,
    "app-470f2e6b8278a0fea9994c7e": 2,
    "app-dbf591b0fd48fd4985d99609": 2,
    "app-0fa00ada4df12cd3081de310": 2,
    "app-25078546eb12a715f8a3d1b8": 2,
    "app-a4d8cbe098478296fb4691a7": 2,
    "app-40761e8342e1bf94df5c7338": 2,
    "app-c4db227826711d6032e86727": 2,
    "app-d9bee133eb462ac25592ffcb": 2,
    "app-d9b9d3397a42bc56d35cd0ef": 2,
    "app-142addf092d49dad155909bf": 2,
    "app-31d149f04de3de94390a11ce": 2,
    "app-70f4eccb4c995840b01b098f": 1,
    "app-7bb632acb232d88045e1b659": 2,
    "app-2256b505c259ec4365c64594": 2,
    "app-98bb795629ae9e7d8271f984": 2
  },
  "expected_site_denominators": {
    "app-692a94fed923f056a6a862fd": 3,
    "app-e3de3e48b34ab6788b7fd88c": 3,
    "app-69ff7af2ff194f3bd06fd4f7": 3,
    "app-9edd3238c39e0ec4f8ba2a4d": 3,
    "app-7997578ee50cd7f69091be58": 3,
    "app-a14a91aa44851afdd6775189": 3,
    "app-d533e3a4791e825199bf2c30": 3,
    "app-2534307b2632cec2f235901d": 3,
    "app-7fbe8bdae7a8b2ade139044b": 3,
    "app-e8ef9bc3028112bc32053886": 2,
    "app-dbc12c0fe08fee9b0d1e2ccf": 1,
    "app-636a2f32f6f61b737150de21": 3,
    "app-95f7633955f9037494bbe989": 3,
    "app-57e27368f9fb3d90ed521bf0": 3,
    "app-f5189cfa26c0bbd0f14c08b1": 3,
    "app-e79976782188a884e4e6d6fe": 3,
    "app-fc64872577d7c22f2d8b2bd0": 3,
    "app-758780c85e102a55d26755b7": 3,
    "app-72e259702360691d76096239": 3,
    "app-3759a408b490a1eec05b8ae0": 2,
    "app-ae9c4c62f5d1362f731e3873": 2,
    "app-0ffd0c8a72d9b9db3da6ca9d": 2,
    "app-d64d6954ab4483412bfb3d4a": 2,
    "app-bc9b5b27eb3c32f1774429d6": 2,
    "app-6cd7b65ba2ab7aa4639301be": 2,
    "app-f8047ab6666258671666046f": 2,
    "app-f26113b93443c5df3770b880": 2,
    "app-e8bb513049e5b87eab79a71d": 1,
    "app-470f2e6b8278a0fea9994c7e": 2,
    "app-dbf591b0fd48fd4985d99609": 2,
    "app-0fa00ada4df12cd3081de310": 2,
    "app-25078546eb12a715f8a3d1b8": 2,
    "app-a4d8cbe098478296fb4691a7": 2,
    "app-40761e8342e1bf94df5c7338": 2,
    "app-c4db227826711d6032e86727": 2,
    "app-d9bee133eb462ac25592ffcb": 2,
    "app-d9b9d3397a42bc56d35cd0ef": 2,
    "app-142addf092d49dad155909bf": 2,
    "app-31d149f04de3de94390a11ce": 2,
    "app-70f4eccb4c995840b01b098f": 1,
    "app-7bb632acb232d88045e1b659": 2,
    "app-2256b505c259ec4365c64594": 2,
    "app-98bb795629ae9e7d8271f984": 2
  },
  "template_denominators": {
    "generic": 8,
    "unselected": 74,
    "operation": 16,
    "long_reading": 2
  },
  "stage_order": [
    "claimed",
    "first_frame",
    "template_selected",
    "model_http",
    "initial_plan_accepted",
    "effective_steps_ge5",
    "goal_verified",
    "formally_saved"
  ],
  "running_snapshot": false,
  "integrity": "FAILED",
  "issues": [
    "fixed_100_claims_incomplete",
    "unsettled_claims"
  ],
  "funnel": {
    "claimed": {
      "independent": 47,
      "prefix": 47,
      "states": {
        "reached": 47,
        "not_reached": 53
      },
      "top5_rejections": []
    },
    "first_frame": {
      "independent": 27,
      "prefix": 27,
      "states": {
        "reached": 27,
        "failed": 20,
        "not_reached": 53
      },
      "top5_rejections": [
        {
          "code": "Error",
          "unique_candidates": 9,
          "events": 9
        },
        {
          "code": "CancelledError",
          "unique_candidates": 7,
          "events": 7
        },
        {
          "code": "EvidenceStale",
          "unique_candidates": 3,
          "events": 3
        },
        {
          "code": "TimeoutError",
          "unique_candidates": 1,
          "events": 1
        }
      ]
    },
    "template_selected": {
      "independent": 26,
      "prefix": 26,
      "states": {
        "reached": 26,
        "not_reached": 73,
        "unknown": 1
      },
      "top5_rejections": []
    },
    "model_http": {
      "independent": 0,
      "prefix": 0,
      "states": {
        "not_reached": 100
      },
      "top5_rejections": []
    },
    "initial_plan_accepted": {
      "independent": 0,
      "prefix": 0,
      "states": {
        "unknown": 27,
        "not_reached": 73
      },
      "top5_rejections": []
    },
    "effective_steps_ge5": {
      "independent": 0,
      "prefix": 0,
      "states": {
        "unknown": 27,
        "not_reached": 73
      },
      "top5_rejections": []
    },
    "goal_verified": {
      "independent": 0,
      "prefix": 0,
      "states": {
        "unknown": 27,
        "not_reached": 73
      },
      "top5_rejections": []
    },
    "formally_saved": {
      "independent": 0,
      "prefix": 0,
      "states": {
        "unknown": 27,
        "not_reached": 73
      },
      "top5_rejections": []
    }
  },
  "by_site": {
    "app-0fa00ada4df12cd3081de310": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 2
        },
        "top5_rejections": [
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          },
          {
            "code": "EvidenceStale",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-0ffd0c8a72d9b9db3da6ca9d": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      }
    },
    "app-142addf092d49dad155909bf": {
      "claimed": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-2256b505c259ec4365c64594": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-25078546eb12a715f8a3d1b8": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 1,
          "not_reached": 1
        },
        "top5_rejections": [
          {
            "code": "TimeoutError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-2534307b2632cec2f235901d": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 3
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 3,
            "events": 3
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      }
    },
    "app-31d149f04de3de94390a11ce": {
      "claimed": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-3759a408b490a1eec05b8ae0": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-40761e8342e1bf94df5c7338": {
      "claimed": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-470f2e6b8278a0fea9994c7e": {
      "claimed": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-57e27368f9fb3d90ed521bf0": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 2,
          "reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 2,
          "reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 2,
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2,
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-636a2f32f6f61b737150de21": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2,
          "not_reached": 1
        },
        "top5_rejections": []
      }
    },
    "app-692a94fed923f056a6a862fd": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-69ff7af2ff194f3bd06fd4f7": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "failed": 1,
          "reached": 2
        },
        "top5_rejections": [
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "not_reached": 1,
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-6cd7b65ba2ab7aa4639301be": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-70f4eccb4c995840b01b098f": {
      "claimed": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      }
    },
    "app-72e259702360691d76096239": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 2,
          "reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      }
    },
    "app-758780c85e102a55d26755b7": {
      "claimed": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      }
    },
    "app-7997578ee50cd7f69091be58": {
      "claimed": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      }
    },
    "app-7bb632acb232d88045e1b659": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "failed": 1,
          "reached": 1
        },
        "top5_rejections": [
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-7fbe8bdae7a8b2ade139044b": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 3
        },
        "top5_rejections": [
          {
            "code": "EvidenceStale",
            "unique_candidates": 2,
            "events": 2
          },
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      }
    },
    "app-95f7633955f9037494bbe989": {
      "claimed": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      }
    },
    "app-98bb795629ae9e7d8271f984": {
      "claimed": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-9edd3238c39e0ec4f8ba2a4d": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "not_reached": 1,
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "not_reached": 1,
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "not_reached": 1,
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-a14a91aa44851afdd6775189": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-a4d8cbe098478296fb4691a7": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 1,
          "not_reached": 1
        },
        "top5_rejections": [
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-ae9c4c62f5d1362f731e3873": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 1,
          "not_reached": 1
        },
        "top5_rejections": [
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-bc9b5b27eb3c32f1774429d6": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-c4db227826711d6032e86727": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-d533e3a4791e825199bf2c30": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 1,
          "not_reached": 2
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      }
    },
    "app-d64d6954ab4483412bfb3d4a": {
      "claimed": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-d9b9d3397a42bc56d35cd0ef": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      }
    },
    "app-d9bee133eb462ac25592ffcb": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "app-dbc12c0fe08fee9b0d1e2ccf": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-dbf591b0fd48fd4985d99609": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "unknown": 1
        },
        "top5_rejections": []
      }
    },
    "app-e3de3e48b34ab6788b7fd88c": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "failed": 1,
          "not_reached": 2
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      }
    },
    "app-e79976782188a884e4e6d6fe": {
      "claimed": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 3,
        "prefix": 3,
        "states": {
          "reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 3
        },
        "top5_rejections": []
      }
    },
    "app-e8bb513049e5b87eab79a71d": {
      "claimed": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1
        },
        "top5_rejections": []
      }
    },
    "app-e8ef9bc3028112bc32053886": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "not_reached": 1,
          "reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "failed": 1
        },
        "top5_rejections": [
          {
            "code": "CancelledError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      }
    },
    "app-f26113b93443c5df3770b880": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      }
    },
    "app-f5189cfa26c0bbd0f14c08b1": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "not_reached": 1,
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 1,
          "failed": 2
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 2,
            "events": 2
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      }
    },
    "app-f8047ab6666258671666046f": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 1
        },
        "top5_rejections": []
      }
    },
    "app-fc64872577d7c22f2d8b2bd0": {
      "claimed": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "reached": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 3
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 1,
          "not_reached": 2
        },
        "top5_rejections": []
      }
    }
  },
  "by_template": {
    "generic": {
      "claimed": {
        "independent": 8,
        "prefix": 8,
        "states": {
          "reached": 8
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 8,
        "prefix": 8,
        "states": {
          "reached": 8
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 8,
        "prefix": 8,
        "states": {
          "reached": 8
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 8
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 8
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 8
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 8
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 8
        },
        "top5_rejections": []
      }
    },
    "long_reading": {
      "claimed": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 2,
        "prefix": 2,
        "states": {
          "reached": 2
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 2
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 2
        },
        "top5_rejections": []
      }
    },
    "operation": {
      "claimed": {
        "independent": 16,
        "prefix": 16,
        "states": {
          "reached": 16
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 16,
        "prefix": 16,
        "states": {
          "reached": 16
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 16,
        "prefix": 16,
        "states": {
          "reached": 16
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 16
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 16
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 16
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 16
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "unknown": 16
        },
        "top5_rejections": []
      }
    },
    "unselected": {
      "claimed": {
        "independent": 21,
        "prefix": 21,
        "states": {
          "reached": 21,
          "not_reached": 53
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 1,
        "prefix": 1,
        "states": {
          "failed": 20,
          "not_reached": 53,
          "reached": 1
        },
        "top5_rejections": [
          {
            "code": "Error",
            "unique_candidates": 9,
            "events": 9
          },
          {
            "code": "CancelledError",
            "unique_candidates": 7,
            "events": 7
          },
          {
            "code": "EvidenceStale",
            "unique_candidates": 3,
            "events": 3
          },
          {
            "code": "TimeoutError",
            "unique_candidates": 1,
            "events": 1
          }
        ]
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 73,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "model_http": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 74
        },
        "top5_rejections": []
      },
      "initial_plan_accepted": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 73,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 73,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 73,
          "unknown": 1
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 73,
          "unknown": 1
        },
        "top5_rejections": []
      }
    }
  },
  "faults": [
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "1d77afc4-1b31-4abd-8719-01e68c1beec9",
      "at": 1794962407.36674,
      "occurrence": 1,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "dc51bbd6-7803-4034-aa1c-d99c05a1790d",
      "at": 1794962408.063472,
      "occurrence": 2,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at axisScale (eval at evaluate (:370:30), <anonymous>:39:18)\n    at axisScale (eval at evaluate (:370:30), <anonymous>:39:18)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "f9f92ae7-eee3-4ede-8632-30abfac4d827",
      "at": 1794962422.078927,
      "occurrence": 3,
      "stop_dispatch": true
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1510:34)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "e32faa2e-915a-4c42-b61f-0e5007ef86ae",
      "at": 1794962429.5138922,
      "occurrence": 4,
      "stop_dispatch": true
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "5a7c68ef-a93f-4062-b743-0c6fb6c4decc",
      "at": 1794962432.860599,
      "occurrence": 5,
      "stop_dispatch": true
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794962470.070187,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963151.33674,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963152.0014038,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963262.435261,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963262.9418628,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963263.1703029,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963263.175943,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963263.264809,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963263.44782,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963263.5249228,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963263.549118,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963263.5499241,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "b520e426-2144-4392-b7b4-1299e49fdacb",
      "at": 1794963263.679745,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963264.048976,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963264.4228458,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963264.469192,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963264.624139,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963264.644471,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963264.778774,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.131252,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.161789,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.226815,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.302418,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.409102,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.4262578,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.528082,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.595592,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963265.697319,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": null,
      "code": "UNSUPPORTED_GEOMETRY",
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1557:30)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "0d3cce26-7d1e-48fb-a62b-252f203bdde9",
      "at": 1794963273.5388339,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": null,
      "code": "UNSUPPORTED_GEOMETRY",
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "199f1bc9-f237-4a59-9bd3-320f01850c2c",
      "at": 1794963278.053258,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963284.05361,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963284.6567092,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963284.730158,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963284.8911731,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963285.097377,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963285.314215,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963296.6257448,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963297.054327,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "6154de7c-7db5-4168-ab39-258ba3312f63",
      "at": 1794963297.143117,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": null,
      "code": "UNSUPPORTED_GEOMETRY",
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1510:34)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "8edafc18-df9f-40b7-a8eb-bcfb661127af",
      "at": 1794963298.266423,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963305.408107,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963306.147605,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963306.440894,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963306.6164439,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963306.733407,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963306.7722082,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963306.948222,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963307.098762,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963307.503293,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963307.571852,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963307.730109,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963324.890219,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.397354,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.4181519,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "6154de7c-7db5-4168-ab39-258ba3312f63",
      "at": 1794963325.4317062,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.474896,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.500617,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.648742,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.658068,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.700288,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.846686,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.9529548,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963325.9751098,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963326.011752,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "b9ed25c6-b541-4362-9272-6a4603429e9f",
      "at": 1794963326.299642,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963332.317557,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963337.524906,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963337.96333,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963338.022321,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "b9ed25c6-b541-4362-9272-6a4603429e9f",
      "at": 1794963349.394512,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963385.336962,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963385.384081,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963385.558626,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963385.575708,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "单帧取证期间未能确认截图与界面树同步，拒绝保存该帧",
      "error_feature": "webcollect.browser.EvidenceStale:browser.py:_capture:692",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "5b2aa771-efea-485a-af15-58776aaf4a45",
      "at": 1794963436.527309,
      "occurrence": 1,
      "stop_dispatch": false
    },
    {
      "reason_owner": "site",
      "retry_count": 0,
      "disposition": "business",
      "failure_class": null,
      "code": "UNSUPPORTED_GEOMETRY",
      "reason": "Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "error_feature": "playwright._impl._errors.Error:_connection.py:wrap_api_call:636",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "b9ed25c6-b541-4362-9272-6a4603429e9f",
      "at": 1794963441.0801249,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "页面同步观察超过15秒，停止该任务并保留检查点",
      "error_feature": "asyncio.exceptions.CancelledError:tasks.py:_wait:521",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "e5df7ea9-5342-42d7-9098-d46bef0002a3",
      "at": 1794963448.741078,
      "occurrence": 1,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "单帧取证期间未能确认截图与界面树同步，拒绝保存该帧",
      "error_feature": "webcollect.browser.EvidenceStale:browser.py:_capture:692",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "4b6de7ba-91b6-4e18-a215-ecf0e9531c7b",
      "at": 1794963455.741327,
      "occurrence": 2,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963472.9499588,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "36176b7e-48e3-4e57-8d0a-e040efab37c2",
      "at": 1794963473.4091341,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963474.772036,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "eb045d64-0d15-477a-8e8e-32765897eb09",
      "at": 1794963518.325621,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963541.0461178,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963555.70512,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963555.750676,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963555.8197389,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963556.2529159,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963556.379483,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963556.4519758,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963556.93963,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963557.092198,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963557.171795,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963557.4282382,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963557.5889459,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963557.755873,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963557.763079,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963557.92367,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963558.299231,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963558.350934,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963558.5019689,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963558.747099,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963558.7794828,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.159892,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.2914188,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.330442,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.62626,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.677517,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.733484,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.9023721,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963559.942219,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963560.792575,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963561.153484,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963561.631289,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963561.805781,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963561.912488,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963562.371089,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963562.516682,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963562.5335739,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963562.955758,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963562.9714508,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963563.0037382,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963563.087048,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "3909246f-658d-486b-acd3-452c33b533eb",
      "at": 1794963563.104488,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "fbb44604-1e02-466c-8736-d110bc1e6154",
      "at": 1794963563.881693,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963564.008121,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963564.857676,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "3909246f-658d-486b-acd3-452c33b533eb",
      "at": 1794963565.260176,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963565.581964,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "fbb44604-1e02-466c-8736-d110bc1e6154",
      "at": 1794963566.035668,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963568.167819,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "3909246f-658d-486b-acd3-452c33b533eb",
      "at": 1794963568.362282,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "fbb44604-1e02-466c-8736-d110bc1e6154",
      "at": 1794963569.17362,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963570.3502479,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 3,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963571.465931,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963571.714855,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963573.863148,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 0,
      "disposition": "page_program",
      "failure_class": null,
      "code": null,
      "reason": "单帧取证期间未能确认截图与界面树同步，拒绝保存该帧",
      "error_feature": "webcollect.browser.EvidenceStale:browser.py:_capture:692",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "fbb44604-1e02-466c-8736-d110bc1e6154",
      "at": 1794963574.471033,
      "occurrence": 3,
      "stop_dispatch": true
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963575.108425,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 1,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963575.6577542,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "unknown",
      "retry_count": 0,
      "disposition": "interrupted",
      "failure_class": null,
      "code": null,
      "reason": "SQLite retry stopped before lock acquisition",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": false,
      "shared_dependency_exhausted": false,
      "claim_id": "fbb44604-1e02-466c-8736-d110bc1e6154",
      "at": 1794963575.6686442,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "reason_owner": "program",
      "retry_count": 2,
      "disposition": "transient",
      "failure_class": "transient",
      "code": null,
      "reason": "database is locked",
      "error_feature": "sqlite3.OperationalError:sqlite_connection.py:execute:44",
      "transient": true,
      "shared_dependency_exhausted": false,
      "operation": "begin_immediate",
      "claim_id": "pre_dispatch",
      "at": 1794963577.700245,
      "occurrence": null,
      "stop_dispatch": false
    },
    {
      "claim_id": "35c17913-93ed-4bb0-ac45-080b1ee9fb2f",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "199f1bc9-f237-4a59-9bd3-320f01850c2c",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "6154de7c-7db5-4168-ab39-258ba3312f63",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "08a42126-7ce4-418c-9698-a4d87310da74",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "0d3cce26-7d1e-48fb-a62b-252f203bdde9",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1557:30)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "b9ed25c6-b541-4362-9272-6a4603429e9f",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "1cdf406f-4507-4cfd-a188-74c3cdf27bea",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "74d2511e-0857-4fff-8129-e9f3503fcb27",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "12e4d392-8636-4b38-97fc-e7dbf4e38846",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "5cb69bde-f2e3-4205-9da8-c3e71180c8fb",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "4bd8565a-bc11-4ba3-ae25-88b2c51f8d93",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "7988b049-2075-4ef6-8ffc-c85e337d07df",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "b520e426-2144-4392-b7b4-1299e49fdacb",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "a443b324-3c36-4279-92ba-74f0e7ff38de",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "97701ec9-07e5-4613-bda4-6a85a902c9a3",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "349b292f-c6b7-4a4e-8e16-b4608824ae78",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "e5df7ea9-5342-42d7-9098-d46bef0002a3",
      "failure_class": null,
      "reason": "TimeoutError: 页面同步观察超过15秒，停止该任务并保留检查点",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "36176b7e-48e3-4e57-8d0a-e040efab37c2",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "a2608120-9306-40ab-be0b-6f382f3f544d",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "aeaedf63-c90c-4925-bebf-ff9cfe9f88ca",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "ef6230c0-9566-457b-86d1-e11c43d2093d",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "5e105f46-7bb0-4dc8-8864-08eb5afd6d76",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "a6841830-30bf-4e6a-9753-88a2d707a725",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "68185304-e686-4481-b21b-13f9d20bc01a",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "1d77afc4-1b31-4abd-8719-01e68c1beec9",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "4b6de7ba-91b6-4e18-a215-ecf0e9531c7b",
      "failure_class": null,
      "reason": "EvidenceStale: 单帧取证期间未能确认截图与界面树同步，拒绝保存该帧",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "eb045d64-0d15-477a-8e8e-32765897eb09",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "c6ceb74c-f349-4f05-b197-39f260349dcb",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "8edafc18-df9f-40b7-a8eb-bcfb661127af",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1510:34)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "1c4fa4e9-e3e3-462d-a791-e56963efd2c3",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "f9f92ae7-eee3-4ede-8632-30abfac4d827",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at axisScale (eval at evaluate (:370:30), <anonymous>:39:18)\n    at axisScale (eval at evaluate (:370:30), <anonymous>:39:18)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "79608024-eeb4-4da4-ac39-be8260070222",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "90972f16-623b-409f-b0d4-2a2d35e4a450",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "77af9c2a-971a-4810-9374-2a6c7e8a72bb",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "f72c6ec8-f47d-4897-9291-a27ff217ca15",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "5a7c68ef-a93f-4062-b743-0c6fb6c4decc",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at eval (eval at evaluate (:370:30), <anonymous>:706:10)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "920721b7-25b7-4f95-a29d-6edef302b7e4",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "e44cd977-9d70-4813-9b7b-20493adc60df",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "e66f8390-d5cc-4660-9492-e904079e5efe",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "cbf160f6-57bf-4350-af15-8a9799283983",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "d388e77b-6eb9-4266-b729-459a308c8118",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "dc51bbd6-7803-4034-aa1c-d99c05a1790d",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:278:16)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)\n    at visibleText (eval at evaluate (:370:30), <anonymous>:264:39)\n    at Array.map (<anonymous>)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "5b2aa771-efea-485a-af15-58776aaf4a45",
      "failure_class": null,
      "reason": "EvidenceStale: 单帧取证期间未能确认截图与界面树同步，拒绝保存该帧",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "3909246f-658d-486b-acd3-452c33b533eb",
      "failure_class": null,
      "reason": "Cancelled without committed complete save; retain original requests and attempts; no resend",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "e32faa2e-915a-4c42-b61f-0e5007ef86ae",
      "failure_class": null,
      "reason": "Error: Page.evaluate: Error: UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth\n    at axisScale (eval at evaluate (:370:30), <anonymous>:37:13)\n    at clipFor (eval at evaluate (:370:30), <anonymous>:55:74)\n    at eval (eval at evaluate (:370:30), <anonymous>:1510:34)\n    at UtilityScript.evaluate (<anonymous>:377:18)\n    at UtilityScript.<anonymous> (<anonymous>:1:44)",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    },
    {
      "claim_id": "2e834a38-66d2-454f-82c6-5776001bdb52",
      "failure_class": null,
      "reason": "CancelledError: ",
      "disposition": "unclassified",
      "reason_owner": "unknown",
      "code": null,
      "retry_count": 0
    }
  ],
  "fault_categories": {
    "page_program": 9,
    "transient": 132,
    "business": 4,
    "interrupted": 1,
    "unclassified": 46
  },
  "reason_owners": {
    "program": 141,
    "site": 4,
    "unknown": 47
  },
  "units": {
    "funnel": "unique frozen candidate",
    "requests": "unique physical request id",
    "tokens": "provider tokens",
    "elapsed": "seconds"
  },
  "usage": {
    "producer": {
      "requests": 317,
      "states": {
        "succeeded": 217,
        "invalid_response": 99,
        "reserved": 1
      },
      "dispatch": {
        "dispatched": 316,
        "unproven": 1
      },
      "input_tokens": null,
      "output_tokens": null,
      "known_input_tokens": 13295846,
      "known_output_tokens": 661345,
      "unknown_usage_requests": 1,
      "cost": "UNKNOWN"
    },
    "consumer": {
      "requests": 0,
      "states": {},
      "dispatch": {},
      "input_tokens": 0,
      "output_tokens": 0,
      "known_input_tokens": 0,
      "known_output_tokens": 0,
      "unknown_usage_requests": 0,
      "cost": "UNKNOWN"
    },
    "startup_probes": {
      "requests": 0,
      "states": {},
      "dispatch": {},
      "input_tokens": 0,
      "output_tokens": 0,
      "known_input_tokens": 0,
      "known_output_tokens": 0,
      "unknown_usage_requests": 0,
      "cost": "UNKNOWN"
    },
    "total": {
      "requests": 317,
      "states": {
        "succeeded": 217,
        "invalid_response": 99,
        "reserved": 1
      },
      "dispatch": {
        "dispatched": 316,
        "unproven": 1
      },
      "input_tokens": null,
      "output_tokens": null,
      "known_input_tokens": 13295846,
      "known_output_tokens": 661345,
      "unknown_usage_requests": 1,
      "cost": "UNKNOWN"
    }
  },
  "unattributed_requests": {
    "consumer": 2565,
    "startup_probes_scope_unknown": false,
    "producer": 1425
  },
  "saved": 0,
  "mean_saved_input_tokens": null,
  "amortized_input_tokens": null,
  "mean_saved_session_seconds": null,
  "mean_saved_output_tokens": null,
  "amortized_output_tokens": null,
  "amortized_session_seconds": null,
  "round_elapsed_seconds": 1052.2595838760026,
  "cache_hits": 0,
  "web_visits": {
    "count": 47,
    "states": {
      "succeeded": 47
    }
  },
  "tool_requests": {
    "count": 0,
    "states": {}
  },
  "candidates": [
    {
      "candidate_id": "candidate-375fd231-0d49-4cd5-b65d-c46182578840",
      "version": 1,
      "application_id": "app-692a94fed923f056a6a862fd",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "35c17913-93ed-4bb0-ac45-080b1ee9fb2f"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-01/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-01/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 135.25426420907024,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-d44f1ec9-dd29-4cd2-a8db-91a05bb3fdf3",
      "version": 1,
      "application_id": "app-e3de3e48b34ab6788b7fd88c",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "199f1bc9-f237-4a59-9bd3-320f01850c2c"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-01/199f1bc9-f237-4a59-9bd3-320f01850c2c/first-observation-failure.json",
              "sha256": "0f99763daec7e551abb0c84bfaddd517a2561bdadf048e12b525e214b70cdfe8"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 141.88086867332458,
      "session_elapsed_seconds": 66.57329520804342,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-2976968d-59af-4881-b3ef-8ddcfc4a40e7",
      "version": 1,
      "application_id": "app-69ff7af2ff194f3bd06fd4f7",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "6154de7c-7db5-4168-ab39-258ba3312f63"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-01/6154de7c-7db5-4168-ab39-258ba3312f63/first-observation-failure.json",
              "sha256": "5d2f0bd57ea3f0371ac0b91a29fec6c05a2431502459128ad2de9646f5993ea1"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 278.96602691698354,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-a9b1993e-d240-461e-85e5-fba71bc7c07a",
      "version": 1,
      "application_id": "app-9edd3238c39e0ec4f8ba2a4d",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-ae35d5a4-66ab-4b5e-a5dd-ae0fa8ab40db",
      "version": 1,
      "application_id": "app-7997578ee50cd7f69091be58",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-d4c160c8-7db5-46b3-9dbf-9bf4420c4291",
      "version": 1,
      "application_id": "app-a14a91aa44851afdd6775189",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "08a42126-7ce4-418c-9698-a4d87310da74"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-02/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-02/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 135.85555441700853,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-89186119-bece-4542-88c4-a10a412fd270",
      "version": 1,
      "application_id": "app-d533e3a4791e825199bf2c30",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "0d3cce26-7d1e-48fb-a62b-252f203bdde9"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-02/0d3cce26-7d1e-48fb-a62b-252f203bdde9/first-observation-failure.json",
              "sha256": "cb3ad5e5d4f10ac317a09792aeff1c7a2c52ccccfa8b102c571a3dc911ba1bc7"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 136.07854008674622,
      "session_elapsed_seconds": 57.101450709044,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-c8bccab8-e411-4a13-966a-c0003f61f8e3",
      "version": 1,
      "application_id": "app-2534307b2632cec2f235901d",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "b9ed25c6-b541-4362-9272-6a4603429e9f"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-02/b9ed25c6-b541-4362-9272-6a4603429e9f/first-observation-failure.json",
              "sha256": "03e318b2b7cf2bb7dea15fbc5a14766997ba97f1d357e4b3de8607e6da3e7c56"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 145.21357583999634,
      "session_elapsed_seconds": 63.141595375025645,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-420eb8bc-5d96-4680-ae3f-7c2873a55b5d",
      "version": 1,
      "application_id": "app-7fbe8bdae7a8b2ade139044b",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "1cdf406f-4507-4cfd-a188-74c3cdf27bea"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-02/1cdf406f-4507-4cfd-a188-74c3cdf27bea/first-observation-failure.json",
              "sha256": "a063ca21404f6210e88506e85462aad761fd556b4acdb60d968e9e26179e76c8"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 83.07121070800349,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-4550c5de-f539-446c-8576-8a0442f6cdf9",
      "version": 1,
      "application_id": "app-e8ef9bc3028112bc32053886",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-b8f7717c-82a1-4fee-b924-5f4010e4fd1f",
      "version": 1,
      "application_id": "app-dbc12c0fe08fee9b0d1e2ccf",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "74d2511e-0857-4fff-8129-e9f3503fcb27"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-03/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-03/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 134.52666983392555,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-a9dd237d-5883-4a9c-9af3-6c28f7da4649",
      "version": 1,
      "application_id": "app-636a2f32f6f61b737150de21",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "12e4d392-8636-4b38-97fc-e7dbf4e38846"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-03/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-03/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 434.0599745409563,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-09333267-7f26-4e54-8631-5ed85b819f1d",
      "version": 1,
      "application_id": "app-95f7633955f9037494bbe989",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-736703cd-f6a0-4315-b700-31b775c1494c",
      "version": 1,
      "application_id": "app-57e27368f9fb3d90ed521bf0",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-3a31daf3-4f68-42e3-a112-b7d471e97f17",
      "version": 1,
      "application_id": "app-f5189cfa26c0bbd0f14c08b1",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-c79499d7-9232-4c7a-b01e-42839583f9d4",
      "version": 1,
      "application_id": "app-e79976782188a884e4e6d6fe",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "5cb69bde-f2e3-4205-9da8-c3e71180c8fb"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-04/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-04/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 130.70122954202816,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-05be67ef-2a34-49d0-8479-09a57a930278",
      "version": 1,
      "application_id": "app-fc64872577d7c22f2d8b2bd0",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "4bd8565a-bc11-4ba3-ae25-88b2c51f8d93"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-04/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-04/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 434.4001774999779,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-c0182846-c964-40ed-9d1d-ed609a464878",
      "version": 1,
      "application_id": "app-758780c85e102a55d26755b7",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-5e35114a-7106-42d7-b0ec-34b651c2523a",
      "version": 1,
      "application_id": "app-72e259702360691d76096239",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-3c556361-c1a3-4acd-bac8-586a306a47a4",
      "version": 1,
      "application_id": "app-3759a408b490a1eec05b8ae0",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-60146573-e1b6-4134-ae87-6f2ac5ac9ba6",
      "version": 1,
      "application_id": "app-ae9c4c62f5d1362f731e3873",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "7988b049-2075-4ef6-8ffc-c85e337d07df"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-05/7988b049-2075-4ef6-8ffc-c85e337d07df/first-observation-failure.json",
              "sha256": "79083408ec281eb598229f4b68bb8415813bce31dc798ce001580574f7d70389"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 123.5636615420226,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-d201e34f-61b9-4262-8e0e-1af7d9a2201b",
      "version": 1,
      "application_id": "app-0ffd0c8a72d9b9db3da6ca9d",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "b520e426-2144-4392-b7b4-1299e49fdacb"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-05/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-05/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 441.2495462500956,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-a24b1534-e3e6-4dc4-9ee3-72dafffd7319",
      "version": 1,
      "application_id": "app-d64d6954ab4483412bfb3d4a",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-26f00cf8-d90c-478e-b7ee-be3fd352cd3d",
      "version": 1,
      "application_id": "app-bc9b5b27eb3c32f1774429d6",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-c5a1a241-479c-46dd-98bc-f36e2cae4ce3",
      "version": 1,
      "application_id": "app-6cd7b65ba2ab7aa4639301be",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-ec31078c-f737-408b-a746-358a73a083ed",
      "version": 1,
      "application_id": "app-f8047ab6666258671666046f",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "a443b324-3c36-4279-92ba-74f0e7ff38de"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-06/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-06/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 117.87452320801094,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-c3b8e1de-61cc-4d42-946c-d8fac99f513d",
      "version": 1,
      "application_id": "app-f26113b93443c5df3770b880",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "97701ec9-07e5-4613-bda4-6a85a902c9a3"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-06/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-06/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 431.25271695898846,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-b42da83e-8934-4deb-9115-74b1a2206ce5",
      "version": 1,
      "application_id": "app-e8bb513049e5b87eab79a71d",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-349828b7-d8cd-4595-a312-07562dc6d962",
      "version": 1,
      "application_id": "app-470f2e6b8278a0fea9994c7e",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-17427055-f5a9-4984-90d6-c7325cf052bf",
      "version": 1,
      "application_id": "app-dbf591b0fd48fd4985d99609",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-6e6d4a28-95bf-43e8-b368-c29bd5587b0a",
      "version": 1,
      "application_id": "app-0fa00ada4df12cd3081de310",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "349b292f-c6b7-4a4e-8e16-b4608824ae78"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-07/349b292f-c6b7-4a4e-8e16-b4608824ae78/first-observation-failure.json",
              "sha256": "2e2b868761a1ee95496d9d60f441713e5b4d87b55750469f2077bcd73a541f2c"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 137.18654583301395,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-79dfd883-f765-484f-9975-9c48f386f4be",
      "version": 1,
      "application_id": "app-25078546eb12a715f8a3d1b8",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "e5df7ea9-5342-42d7-9098-d46bef0002a3"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "TimeoutError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-07/e5df7ea9-5342-42d7-9098-d46bef0002a3/first-observation-failure.json",
              "sha256": "2f526bcb1bc0313f3ab26ed43141b09ca120f9f485eb5e71dc47be1cb767f7ad"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 232.2881142909173,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-8925f228-1c19-4059-9e8b-dd65cc52379d",
      "version": 1,
      "application_id": "app-a4d8cbe098478296fb4691a7",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "36176b7e-48e3-4e57-8d0a-e040efab37c2"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-07/36176b7e-48e3-4e57-8d0a-e040efab37c2/first-observation-failure.json",
              "sha256": "a030577ff8181d54abb5999e8a35578ec15d7e6a3c64490e412b9f9125c33ed1"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 82.40674754104111,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-5110f7b6-65e1-4dd0-8fa4-2e38d012dceb",
      "version": 1,
      "application_id": "app-40761e8342e1bf94df5c7338",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-103dfbff-5206-46e7-983d-f4d87437fba6",
      "version": 1,
      "application_id": "app-c4db227826711d6032e86727",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-46f027af-b010-4e67-b3d7-66f6a1c639ab",
      "version": 1,
      "application_id": "app-d9bee133eb462ac25592ffcb",
      "template": "long_reading",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "a2608120-9306-40ab-be0b-6f382f3f544d"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-08/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-08/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 124.98788816703018,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-e1979b2d-6c92-496f-8084-e98cd5aef88c",
      "version": 1,
      "application_id": "app-d9b9d3397a42bc56d35cd0ef",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "aeaedf63-c90c-4925-bebf-ff9cfe9f88ca"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-08/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-08/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 411.5707942500012,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-1e0661d8-89dd-4819-9bcd-be2ceb510c4a",
      "version": 1,
      "application_id": "app-142addf092d49dad155909bf",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-f6e47429-ed83-4dc5-9f96-f75bbb0efb9f",
      "version": 1,
      "application_id": "app-31d149f04de3de94390a11ce",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-6529c885-7105-4744-b748-d0d4001993fb",
      "version": 1,
      "application_id": "app-70f4eccb4c995840b01b098f",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-5eb6a109-4072-45ea-9777-04ab4b5cefcb",
      "version": 1,
      "application_id": "app-7bb632acb232d88045e1b659",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "ef6230c0-9566-457b-86d1-e11c43d2093d"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-09/ef6230c0-9566-457b-86d1-e11c43d2093d/first-observation-failure.json",
              "sha256": "62228a7d8cdb3229c0970b7a5c50647cc28b21419038e57389d6fc96b4d2b2cb"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 131.65656024997588,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-b16312a7-648d-4d6e-a204-5fd93e9bffb0",
      "version": 1,
      "application_id": "app-2256b505c259ec4365c64594",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "5e105f46-7bb0-4dc8-8864-08eb5afd6d76"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-09/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-09/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 434.898493124987,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-65629fca-6ce0-4175-9fe0-098221f52915",
      "version": 1,
      "application_id": "app-98bb795629ae9e7d8271f984",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-4242ca9c-e23c-4219-bd2b-6a7ecfc40b84",
      "version": 1,
      "application_id": "app-692a94fed923f056a6a862fd",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-78befcac-eb64-46f7-8c94-66a4b772383b",
      "version": 1,
      "application_id": "app-e3de3e48b34ab6788b7fd88c",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-f9857de6-6f63-4ba5-b9cd-04cc9db131d4",
      "version": 1,
      "application_id": "app-69ff7af2ff194f3bd06fd4f7",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "a6841830-30bf-4e6a-9753-88a2d707a725"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-10/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-10/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 134.65049554104917,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-ccd4bf5b-0bec-4102-924a-b2861fd99d53",
      "version": 1,
      "application_id": "app-9edd3238c39e0ec4f8ba2a4d",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "68185304-e686-4481-b21b-13f9d20bc01a"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-10/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-10/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 432.0335450830171,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-96ce87ee-2cdb-4662-a9ad-3246904f1ece",
      "version": 1,
      "application_id": "app-7997578ee50cd7f69091be58",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-adc5f986-a041-4a3a-ae89-f5e3005b6716",
      "version": 1,
      "application_id": "app-a14a91aa44851afdd6775189",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-0937c35c-26c7-454e-8b5b-2376aea5e73f",
      "version": 1,
      "application_id": "app-d533e3a4791e825199bf2c30",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-3bf907ee-906b-4412-92f5-022725fff53d",
      "version": 1,
      "application_id": "app-2534307b2632cec2f235901d",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "1d77afc4-1b31-4abd-8719-01e68c1beec9"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-11/1d77afc4-1b31-4abd-8719-01e68c1beec9/first-observation-failure.json",
              "sha256": "6ce4cf4cf7a8740f052e618e19a09ba31250de14bf7b572ae861fdbf6a91f7cc"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 116.70210695266724,
      "session_elapsed_seconds": 60.06035499996506,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-be57fa9e-87eb-467e-9798-0f44c73d6216",
      "version": 1,
      "application_id": "app-7fbe8bdae7a8b2ade139044b",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "4b6de7ba-91b6-4e18-a215-ecf0e9531c7b"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "EvidenceStale",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-11/4b6de7ba-91b6-4e18-a215-ecf0e9531c7b/first-observation-failure.json",
              "sha256": "a2297e264569effc30cd743114ff7f80ac782ead8f5e9d17da22f25614c63acc"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 321.0930471420288,
      "session_elapsed_seconds": 257.31809737498406,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-a7a8b472-d803-4e92-b5df-cdccad9a1fa9",
      "version": 1,
      "application_id": "app-e8ef9bc3028112bc32053886",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "eb045d64-0d15-477a-8e8e-32765897eb09"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "CancelledError",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-11/eb045d64-0d15-477a-8e8e-32765897eb09/first-observation-failure.json",
              "sha256": "f0fabd7c3ffae1909e232de7b5e140558d8f46693798ec279483ce41d1f9be8e"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 82.50402729108464,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-f5c4f5df-af7d-4e90-9a38-57694392d771",
      "version": 1,
      "application_id": "app-636a2f32f6f61b737150de21",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-5e7ebee4-fe98-4799-8bd2-610a05e29b48",
      "version": 1,
      "application_id": "app-95f7633955f9037494bbe989",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-6807133c-a054-4369-950e-7ffd52a74240",
      "version": 1,
      "application_id": "app-57e27368f9fb3d90ed521bf0",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "c6ceb74c-f349-4f05-b197-39f260349dcb"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-12/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-12/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 132.1373826659983,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-5476dfbe-afe9-4fcf-98d0-c858584d5a08",
      "version": 1,
      "application_id": "app-f5189cfa26c0bbd0f14c08b1",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "8edafc18-df9f-40b7-a8eb-bcfb661127af"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-12/8edafc18-df9f-40b7-a8eb-bcfb661127af/first-observation-failure.json",
              "sha256": "826312ab9361e13a080defcceaea14d52efa0263d19a6cf6dcd1fc524ef3a7f5"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 146.7670979499817,
      "session_elapsed_seconds": 81.84340641694143,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-aa9fc6ea-024f-41f8-a848-90113487172c",
      "version": 1,
      "application_id": "app-e79976782188a884e4e6d6fe",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "1c4fa4e9-e3e3-462d-a791-e56963efd2c3"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-12/runtime.jsonl",
              "line": 14
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-12/runtime.jsonl",
              "line": 16
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 224.40358724992257,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-eaae91a3-e828-4532-8df5-335fe9528901",
      "version": 1,
      "application_id": "app-fc64872577d7c22f2d8b2bd0",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-3b68cc32-3a66-4903-a0fd-dfe9a7acff8e",
      "version": 1,
      "application_id": "app-758780c85e102a55d26755b7",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-bdafa2fc-357a-4919-b516-962efb579911",
      "version": 1,
      "application_id": "app-72e259702360691d76096239",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "f9f92ae7-eee3-4ede-8632-30abfac4d827"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-13/f9f92ae7-eee3-4ede-8632-30abfac4d827/first-observation-failure.json",
              "sha256": "fa18134ab256d305739879221beea419828d8d7e622c069b165eac255e19fdcf"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 123.28526592254639,
      "session_elapsed_seconds": 70.32241870788857,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-add30cf0-8ea5-4f86-9e07-d3bb8d8e0372",
      "version": 1,
      "application_id": "app-3759a408b490a1eec05b8ae0",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "79608024-eeb4-4da4-ac39-be8260070222"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-13/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-13/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 445.469779041945,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-982d6923-48c3-4e2c-ab94-08337fecd2a0",
      "version": 1,
      "application_id": "app-ae9c4c62f5d1362f731e3873",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-ece9b97b-8899-4d29-8228-d637525415bf",
      "version": 1,
      "application_id": "app-0ffd0c8a72d9b9db3da6ca9d",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-a209ea59-e22f-40cd-bd8a-ba00b22e9db9",
      "version": 1,
      "application_id": "app-d64d6954ab4483412bfb3d4a",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-c9a4af0b-c2d4-4134-b0b7-579798b6dc5b",
      "version": 1,
      "application_id": "app-bc9b5b27eb3c32f1774429d6",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "90972f16-623b-409f-b0d4-2a2d35e4a450"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-14/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-14/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 120.61786654195748,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-733e5c29-3536-46bc-80ba-cf201dc6811b",
      "version": 1,
      "application_id": "app-6cd7b65ba2ab7aa4639301be",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "77af9c2a-971a-4810-9374-2a6c7e8a72bb"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-14/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-14/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 414.0084671250079,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-f45aa53f-90ae-41c2-a756-820078cd2671",
      "version": 1,
      "application_id": "app-f8047ab6666258671666046f",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-911ccf31-e8bf-46e9-a877-3be283ff0581",
      "version": 1,
      "application_id": "app-f26113b93443c5df3770b880",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-443c8926-6101-44a0-b0a0-b68c605f9f4d",
      "version": 1,
      "application_id": "app-470f2e6b8278a0fea9994c7e",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-9cb15540-3bc8-4d07-8bcc-054216b5f5d2",
      "version": 1,
      "application_id": "app-dbf591b0fd48fd4985d99609",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "f72c6ec8-f47d-4897-9291-a27ff217ca15"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-15/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-15/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 129.22083762509283,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-b9fb3c1f-47b2-4e26-aac9-a17c2b26fab0",
      "version": 1,
      "application_id": "app-0fa00ada4df12cd3081de310",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "fbb44604-1e02-466c-8736-d110bc1e6154"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "EvidenceStale",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-15/fbb44604-1e02-466c-8736-d110bc1e6154/first-observation-failure.json",
              "sha256": "678c840aa8a521ef6bf8270e30249be639dd92112acff062ccc503ab987b3230"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 346.62695562501904,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-548ed845-f414-48ce-b396-a2ce8c043bc6",
      "version": 1,
      "application_id": "app-25078546eb12a715f8a3d1b8",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-fd0e5779-2c97-4cf9-8774-cd106b04bc27",
      "version": 1,
      "application_id": "app-a4d8cbe098478296fb4691a7",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-0c7dc0fa-6003-4e6f-b568-3f0771dd009e",
      "version": 1,
      "application_id": "app-40761e8342e1bf94df5c7338",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-60668b3c-97bf-43fb-996b-eb12e173887d",
      "version": 1,
      "application_id": "app-c4db227826711d6032e86727",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "5a7c68ef-a93f-4062-b743-0c6fb6c4decc"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-16/5a7c68ef-a93f-4062-b743-0c6fb6c4decc/first-observation-failure.json",
              "sha256": "a87ee26914c9750cf46ba776fb14b98fb7775b429d929b2f55a621faa096101e"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 133.16744709014893,
      "session_elapsed_seconds": 85.1361702500144,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-614e4867-8405-472e-be75-052251059878",
      "version": 1,
      "application_id": "app-d9bee133eb462ac25592ffcb",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "920721b7-25b7-4f95-a29d-6edef302b7e4"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-16/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-16/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 443.3871402500663,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-0bdd2528-8579-42f5-8ebc-2006e0ba2bc3",
      "version": 1,
      "application_id": "app-d9b9d3397a42bc56d35cd0ef",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-d4e895fe-fd3c-4d60-9c1a-7d5add220050",
      "version": 1,
      "application_id": "app-142addf092d49dad155909bf",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-0152558e-3d8d-433e-8813-957d6ab51558",
      "version": 1,
      "application_id": "app-31d149f04de3de94390a11ce",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-755e6d12-178b-40ba-8eb2-07180fe8417c",
      "version": 1,
      "application_id": "app-7bb632acb232d88045e1b659",
      "template": "long_reading",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "e44cd977-9d70-4813-9b7b-20493adc60df"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-17/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-17/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 132.7954962910153,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-d9f815d5-edbc-4420-aefc-17aebb00ca8d",
      "version": 1,
      "application_id": "app-2256b505c259ec4365c64594",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "e66f8390-d5cc-4660-9492-e904079e5efe"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-17/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-17/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 431.523907625,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-43a1498b-45f4-4164-90e6-4becc87fb4c2",
      "version": 1,
      "application_id": "app-98bb795629ae9e7d8271f984",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-fa07d8e3-1863-4d61-b320-4c9cbb9c388c",
      "version": 1,
      "application_id": "app-692a94fed923f056a6a862fd",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-1fa4dd1c-193b-434a-a146-0f79f8723594",
      "version": 1,
      "application_id": "app-e3de3e48b34ab6788b7fd88c",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-3d0cb7be-5140-4514-930f-a3b196406300",
      "version": 1,
      "application_id": "app-69ff7af2ff194f3bd06fd4f7",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "cbf160f6-57bf-4350-af15-8a9799283983"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-18/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-02/runtime/fixed-20261118083453-89960362-18/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 138.14666287507862,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-6988387d-88f5-487c-826d-b569b8f533fb",
      "version": 1,
      "application_id": "app-9edd3238c39e0ec4f8ba2a4d",
      "template": "generic",
      "template_source": "generic_fallback",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "d388e77b-6eb9-4266-b729-459a308c8118"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-18/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-18/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 435.35918958403636,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-c5693ffd-64bb-4ec8-b695-0068448678e0",
      "version": 1,
      "application_id": "app-7997578ee50cd7f69091be58",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-d9a660fc-f040-48e1-b95a-969ae6300f51",
      "version": 1,
      "application_id": "app-a14a91aa44851afdd6775189",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-ae6d2bba-aad5-48e2-a65a-81e3fd9692bf",
      "version": 1,
      "application_id": "app-d533e3a4791e825199bf2c30",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-56eb5eb2-e8bd-4601-a30f-c0077c21c4e8",
      "version": 1,
      "application_id": "app-2534307b2632cec2f235901d",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "dc51bbd6-7803-4034-aa1c-d99c05a1790d"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-19/dc51bbd6-7803-4034-aa1c-d99c05a1790d/first-observation-failure.json",
              "sha256": "fee6e0f09c0c2aeb154f222951b2b503210a9dd338b722876ad4e5c16f027518"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 116.05812883377075,
      "session_elapsed_seconds": 59.257773499935865,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-f7389a74-7be3-4c27-8fcb-ee07aa7eb2c6",
      "version": 1,
      "application_id": "app-7fbe8bdae7a8b2ade139044b",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "5b2aa771-efea-485a-af15-58776aaf4a45"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "EvidenceStale",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118084955-79a8ade5/fixed-20261118084955-79a8ade5-19/5b2aa771-efea-485a-af15-58776aaf4a45/first-observation-failure.json",
              "sha256": "9ee4a76a33ce7ecbb63caa8fa6d344613bfdd1b3cf619bcd2f78586f40fa31ad"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 296.6131100654602,
      "session_elapsed_seconds": 222.7153674159199,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-28eecdec-64b4-4ba5-8b78-537347741125",
      "version": 1,
      "application_id": "app-636a2f32f6f61b737150de21",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "3909246f-658d-486b-acd3-452c33b533eb"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-19/runtime.jsonl",
              "line": 14
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 76.74005337501876,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-8b1b8428-f500-4dea-979f-c800d83e7f0e",
      "version": 1,
      "application_id": "app-95f7633955f9037494bbe989",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-2756e068-26c4-44bf-a3e5-ef7eb4e63f97",
      "version": 1,
      "application_id": "app-57e27368f9fb3d90ed521bf0",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-e6125765-b9df-4499-a4bd-40acd3ec1b70",
      "version": 1,
      "application_id": "app-f5189cfa26c0bbd0f14c08b1",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "e32faa2e-915a-4c42-b61f-0e5007ef86ae"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "failed",
          "code": "Error",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/producer-muxtly-wiki-200-20261111-r01/collections/consumer/20261118083453-89960362/fixed-20261118083453-89960362-20/e32faa2e-915a-4c42-b61f-0e5007ef86ae/first-observation-failure.json",
              "sha256": "c124eb277d0e13ddf327220a05fd218d4e1f5756f4493d89dec4267ec85a22c0"
            }
          ],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": 129.68850898742676,
      "session_elapsed_seconds": 75.84302899998147,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": true,
      "task_terminal_proven": true,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-18afbdac-19bb-4233-b430-5b3e6b2c73d9",
      "version": 1,
      "application_id": "app-e79976782188a884e4e6d6fe",
      "template": "operation",
      "template_source": "page_match",
      "stages": {
        "claimed": {
          "state": "reached",
          "evidence": [
            {
              "table": "candidate_claims",
              "claim_id": "2e834a38-66d2-454f-82c6-5776001bdb52"
            }
          ],
          "prefix_reached": true
        },
        "first_frame": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-20/runtime.jsonl",
              "line": 5
            }
          ],
          "prefix_reached": true
        },
        "template_selected": {
          "state": "reached",
          "evidence": [
            {
              "path": "/Users/hemiao/projects/2610/WebCollect/results/table2-strategy2-100-20261118/run-03/runtime/fixed-20261118084955-79a8ade5-20/runtime.jsonl",
              "line": 7
            }
          ],
          "prefix_reached": true
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "unknown",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": 440.6283785420237,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-507d59f7-6ae6-41aa-95e4-131f1ad610e9",
      "version": 1,
      "application_id": "app-fc64872577d7c22f2d8b2bd0",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-133749d6-1200-400b-879b-9988f4dd69cb",
      "version": 1,
      "application_id": "app-758780c85e102a55d26755b7",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    },
    {
      "candidate_id": "candidate-8796ff60-67b6-4378-9b9a-7f017ea699ca",
      "version": 1,
      "application_id": "app-72e259702360691d76096239",
      "template": "unselected",
      "template_source": null,
      "stages": {
        "claimed": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "first_frame": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "template_selected": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "model_http": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "initial_plan_accepted": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "effective_steps_ge5": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "goal_verified": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        },
        "formally_saved": {
          "state": "not_reached",
          "evidence": [],
          "prefix_reached": false
        }
      },
      "inconsistencies": [],
      "claim_elapsed_seconds": null,
      "session_elapsed_seconds": null,
      "effective_steps": null,
      "first_request_plan_accepted": null,
      "closure_proven": false,
      "task_terminal_proven": false,
      "requests": {
        "requests": 0,
        "states": {},
        "dispatch": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "unknown_usage_requests": 0,
        "cost": "UNKNOWN"
      }
    }
  ],
  "qc": "NOT_RUN",
  "human_review": "NOT_RUN",
  "published": false,
  "acceptance": "UNKNOWN"
}
```

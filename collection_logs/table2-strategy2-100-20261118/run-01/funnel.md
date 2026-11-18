# Collection funnel

Denominator: 100; integrity: FAILED; saved: 0.
| Stage | Independent | Prefix | States |
|---|---:|---:|---|
| claimed | 0 | 0 | {"not_reached": 100} |
| first_frame | 0 | 0 | {"not_reached": 100} |
| template_selected | 0 | 0 | {"not_reached": 100} |
| model_http | 0 | 0 | {"not_reached": 100} |
| initial_plan_accepted | 0 | 0 | {"not_reached": 100} |
| effective_steps_ge5 | 0 | 0 | {"not_reached": 100} |
| goal_verified | 0 | 0 | {"not_reached": 100} |
| formally_saved | 0 | 0 | {"not_reached": 100} |

Usage and per-candidate evidence are in funnel.json.

Issues: ["fixed_100_claims_incomplete"]

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
    "unselected": 100
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
    "fixed_100_claims_incomplete"
  ],
  "funnel": {
    "claimed": {
      "independent": 0,
      "prefix": 0,
      "states": {
        "not_reached": 100
      },
      "top5_rejections": []
    },
    "first_frame": {
      "independent": 0,
      "prefix": 0,
      "states": {
        "not_reached": 100
      },
      "top5_rejections": []
    },
    "template_selected": {
      "independent": 0,
      "prefix": 0,
      "states": {
        "not_reached": 100
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
        "not_reached": 100
      },
      "top5_rejections": []
    },
    "effective_steps_ge5": {
      "independent": 0,
      "prefix": 0,
      "states": {
        "not_reached": 100
      },
      "top5_rejections": []
    },
    "goal_verified": {
      "independent": 0,
      "prefix": 0,
      "states": {
        "not_reached": 100
      },
      "top5_rejections": []
    },
    "formally_saved": {
      "independent": 0,
      "prefix": 0,
      "states": {
        "not_reached": 100
      },
      "top5_rejections": []
    }
  },
  "by_site": {
    "app-0fa00ada4df12cd3081de310": {
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
    "app-0ffd0c8a72d9b9db3da6ca9d": {
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
    "app-25078546eb12a715f8a3d1b8": {
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
    "app-2534307b2632cec2f235901d": {
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
    "app-636a2f32f6f61b737150de21": {
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
    "app-692a94fed923f056a6a862fd": {
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
    "app-69ff7af2ff194f3bd06fd4f7": {
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
    "app-6cd7b65ba2ab7aa4639301be": {
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
    "app-7fbe8bdae7a8b2ade139044b": {
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
    "app-a14a91aa44851afdd6775189": {
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
    "app-a4d8cbe098478296fb4691a7": {
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
    "app-ae9c4c62f5d1362f731e3873": {
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
    "app-bc9b5b27eb3c32f1774429d6": {
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
    "app-c4db227826711d6032e86727": {
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
    "app-d533e3a4791e825199bf2c30": {
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
    "app-d9bee133eb462ac25592ffcb": {
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
    "app-dbc12c0fe08fee9b0d1e2ccf": {
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
    "app-dbf591b0fd48fd4985d99609": {
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
    "app-e3de3e48b34ab6788b7fd88c": {
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
    "app-e79976782188a884e4e6d6fe": {
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
    "app-f26113b93443c5df3770b880": {
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
    "app-f5189cfa26c0bbd0f14c08b1": {
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
    "app-f8047ab6666258671666046f": {
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
    "app-fc64872577d7c22f2d8b2bd0": {
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
    }
  },
  "by_template": {
    "unselected": {
      "claimed": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 100
        },
        "top5_rejections": []
      },
      "first_frame": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 100
        },
        "top5_rejections": []
      },
      "template_selected": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 100
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
          "not_reached": 100
        },
        "top5_rejections": []
      },
      "effective_steps_ge5": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 100
        },
        "top5_rejections": []
      },
      "goal_verified": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 100
        },
        "top5_rejections": []
      },
      "formally_saved": {
        "independent": 0,
        "prefix": 0,
        "states": {
          "not_reached": 100
        },
        "top5_rejections": []
      }
    }
  },
  "faults": [],
  "fault_categories": {},
  "reason_owners": {},
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
    "startup_probes_scope_unknown": true,
    "producer": 1425
  },
  "saved": 0,
  "mean_saved_input_tokens": null,
  "amortized_input_tokens": null,
  "mean_saved_session_seconds": null,
  "mean_saved_output_tokens": null,
  "amortized_output_tokens": null,
  "amortized_session_seconds": null,
  "round_elapsed_seconds": 92.61988637491595,
  "cache_hits": 0,
  "web_visits": {
    "count": 0,
    "states": {}
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
      "candidate_id": "candidate-d44f1ec9-dd29-4cd2-a8db-91a05bb3fdf3",
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
      "candidate_id": "candidate-2976968d-59af-4881-b3ef-8ddcfc4a40e7",
      "version": 1,
      "application_id": "app-69ff7af2ff194f3bd06fd4f7",
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
      "candidate_id": "candidate-89186119-bece-4542-88c4-a10a412fd270",
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
      "candidate_id": "candidate-c8bccab8-e411-4a13-966a-c0003f61f8e3",
      "version": 1,
      "application_id": "app-2534307b2632cec2f235901d",
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
      "candidate_id": "candidate-420eb8bc-5d96-4680-ae3f-7c2873a55b5d",
      "version": 1,
      "application_id": "app-7fbe8bdae7a8b2ade139044b",
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
      "candidate_id": "candidate-a9dd237d-5883-4a9c-9af3-6c28f7da4649",
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
      "candidate_id": "candidate-05be67ef-2a34-49d0-8479-09a57a930278",
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
      "candidate_id": "candidate-d201e34f-61b9-4262-8e0e-1af7d9a2201b",
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
      "candidate_id": "candidate-c3b8e1de-61cc-4d42-946c-d8fac99f513d",
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
      "candidate_id": "candidate-79dfd883-f765-484f-9975-9c48f386f4be",
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
      "candidate_id": "candidate-8925f228-1c19-4059-9e8b-dd65cc52379d",
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
      "candidate_id": "candidate-e1979b2d-6c92-496f-8084-e98cd5aef88c",
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
      "candidate_id": "candidate-b16312a7-648d-4d6e-a204-5fd93e9bffb0",
      "version": 1,
      "application_id": "app-2256b505c259ec4365c64594",
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
      "candidate_id": "candidate-ccd4bf5b-0bec-4102-924a-b2861fd99d53",
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
      "candidate_id": "candidate-be57fa9e-87eb-467e-9798-0f44c73d6216",
      "version": 1,
      "application_id": "app-7fbe8bdae7a8b2ade139044b",
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
      "candidate_id": "candidate-a7a8b472-d803-4e92-b5df-cdccad9a1fa9",
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
      "candidate_id": "candidate-5476dfbe-afe9-4fcf-98d0-c858584d5a08",
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
      "candidate_id": "candidate-aa9fc6ea-024f-41f8-a848-90113487172c",
      "version": 1,
      "application_id": "app-e79976782188a884e4e6d6fe",
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
      "candidate_id": "candidate-add30cf0-8ea5-4f86-9e07-d3bb8d8e0372",
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
      "candidate_id": "candidate-733e5c29-3536-46bc-80ba-cf201dc6811b",
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
      "candidate_id": "candidate-b9fb3c1f-47b2-4e26-aac9-a17c2b26fab0",
      "version": 1,
      "application_id": "app-0fa00ada4df12cd3081de310",
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
      "candidate_id": "candidate-614e4867-8405-472e-be75-052251059878",
      "version": 1,
      "application_id": "app-d9bee133eb462ac25592ffcb",
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
      "candidate_id": "candidate-d9f815d5-edbc-4420-aefc-17aebb00ca8d",
      "version": 1,
      "application_id": "app-2256b505c259ec4365c64594",
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
      "candidate_id": "candidate-6988387d-88f5-487c-826d-b569b8f533fb",
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
      "candidate_id": "candidate-f7389a74-7be3-4c27-8fcb-ee07aa7eb2c6",
      "version": 1,
      "application_id": "app-7fbe8bdae7a8b2ade139044b",
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
      "candidate_id": "candidate-28eecdec-64b4-4ba5-8b78-537347741125",
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
      "candidate_id": "candidate-18afbdac-19bb-4233-b430-5b3e6b2c73d9",
      "version": 1,
      "application_id": "app-e79976782188a884e4e6d6fe",
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
